"""
PayTraq API Client
------------------
Shared HTTP layer for all PayTraq MCP tools.

Responsibilities:
  - Authenticated requests (APIToken + APIKey) read at call-time from env.
  - UTF-8 decoding of XML responses (PayTraq omits the charset header).
  - Token-bucket rate limiting: 1 req/sec avg, burst 5, 5000 req/day.
  - Retry on 429 / 5xx / timeouts with exponential back-off.
  - XML <-> dict conversion, including list-of-items support for line items.
  - Pagination metadata (has_more / next_page / count) for list endpoints.
  - Two response formats: JSON (structured) and Markdown (human-readable).

PayTraq returns different error shapes for different failure modes.
This module normalises them into PaytraqError so tools can raise a single
type and FastMCP reports isError=True with an actionable message.
"""

from __future__ import annotations

import json
import os
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import httpx

BASE_URL = "https://go.paytraq.com/api"
PAGE_SIZE = 100
DEFAULT_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
CHARACTER_LIMIT = 25_000
DEFAULT_LIST_LIMIT = 50

UTC = timezone.utc


# ── Exceptions ────────────────────────────────────────────────────────────────

class PaytraqError(RuntimeError):
    """Normalised PayTraq API error. The message is the text shown to the LLM."""


class PaytraqAuthError(PaytraqError):
    """401/403 — credentials missing, wrong, or lacking permission."""


class PaytraqNotFound(PaytraqError):
    """404 — no such resource."""


class PaytraqBadRequest(PaytraqError):
    """400 — invalid parameters / body."""


class PaytraqRateLimit(PaytraqError):
    """429 or daily quota exhausted."""


# ── Rate limiter ──────────────────────────────────────────────────────────────

class RateLimiter:
    """Token-bucket limiter. PayTraq: 1 req/sec avg, burst up to 5, 5000/day."""

    def __init__(self, rate: float = 1.0, burst: int = 5, daily_limit: int = 5000):
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_refill = time.monotonic()
        self.daily_limit = daily_limit
        self.daily_count = 0
        self.daily_reset = datetime.now(UTC).date()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            today = datetime.now(UTC).date()
            if today != self.daily_reset:
                self.daily_count = 0
                self.daily_reset = today

            if self.daily_count >= self.daily_limit:
                raise PaytraqRateLimit(
                    f"PayTraq daily request quota reached ({self.daily_limit}). "
                    "Quota resets at 00:00 UTC. Retry after midnight or reduce call volume."
                )

            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_refill = now

            if self.tokens < 1:
                wait = (1 - self.tokens) / self.rate
                time.sleep(wait)
                self.tokens = 0
            else:
                self.tokens -= 1

            self.daily_count += 1


_limiter = RateLimiter()


# ── Persistent HTTP client ────────────────────────────────────────────────────

_http_client: Optional[httpx.Client] = None
_http_client_lock = threading.Lock()


def _get_client() -> httpx.Client:
    global _http_client
    with _http_client_lock:
        if _http_client is None:
            _http_client = httpx.Client(
                timeout=DEFAULT_TIMEOUT_SECONDS,
                headers={"Accept": "application/xml"},
            )
    return _http_client


def close() -> None:
    """Close the shared HTTP client. Safe to call at shutdown."""
    global _http_client
    with _http_client_lock:
        if _http_client is not None:
            _http_client.close()
            _http_client = None


# ── XML helpers ───────────────────────────────────────────────────────────────

def _xml_to_value(element: ET.Element) -> Any:
    children = list(element)
    if not children:
        return (element.text or "").strip()

    result: dict[str, Any] = {}
    for child in children:
        value = _xml_to_value(child)
        if child.tag in result:
            existing = result[child.tag]
            if not isinstance(existing, list):
                result[child.tag] = [existing]
            result[child.tag].append(value)
        else:
            result[child.tag] = value
    return result


def parse_xml(text: str) -> dict:
    """Parse a PayTraq XML response into a dict. Returns {root_tag: body}."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise PaytraqError(
            f"PayTraq returned malformed XML ({exc}). Raw (first 300 chars): {text[:300]!r}"
        ) from exc
    return {root.tag: _xml_to_value(root)}


def _append(parent: ET.Element, key: str, value: Any) -> None:
    """Append a dict/list/scalar as XML under `parent` with tag `key`."""
    if isinstance(value, list):
        for item in value:
            _append(parent, key, item)
        return

    child = ET.SubElement(parent, key)
    if isinstance(value, dict):
        for k, v in value.items():
            _append(child, k, v)
    elif isinstance(value, bool):
        child.text = "true" if value else "false"
    elif value is None:
        return
    else:
        child.text = str(value)


def build_xml(root_tag: str, data: dict) -> str:
    """
    Build an XML string from a dict. Lists are serialised as repeated elements —
    essential for PayTraq line items where {"LineItems": {"LineItem": [...]}}
    must become <LineItems><LineItem>...</LineItem><LineItem>...</LineItem></LineItems>.
    """
    root = ET.Element(root_tag)
    for key, value in data.items():
        _append(root, key, value)
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


# ── Request core ──────────────────────────────────────────────────────────────

def _credentials() -> tuple[str, str]:
    token = os.environ.get("PAYTRAQ_API_TOKEN", "").strip()
    key = os.environ.get("PAYTRAQ_API_KEY", "").strip()
    if not token or not key:
        raise PaytraqAuthError(
            "PAYTRAQ_API_TOKEN and PAYTRAQ_API_KEY environment variables are required. "
            "Find them in PayTraq -> Settings -> API, then restart the MCP server."
        )
    return token, key


def _status_error(status: int, text: str, path: str) -> PaytraqError:
    snippet = text.strip()[:300]
    if status == 400:
        return PaytraqBadRequest(
            f"PayTraq rejected the request to '{path}' (400 Bad Request). "
            f"Check field names/values and required fields. Response: {snippet}"
        )
    if status == 401:
        return PaytraqAuthError(
            "PayTraq 401 Unauthorized. PAYTRAQ_API_TOKEN or PAYTRAQ_API_KEY is wrong "
            "or expired — regenerate in PayTraq -> Settings -> API."
        )
    if status == 403:
        return PaytraqAuthError(
            f"PayTraq 403 Forbidden for '{path}'. Your API credentials do not permit this action."
        )
    if status == 404:
        return PaytraqNotFound(
            f"PayTraq resource '{path}' not found. Double-check the ID or that the "
            "endpoint is spelled correctly (camelCase: e.g. taxKeys, clientGroups)."
        )
    if status == 429:
        return PaytraqRateLimit(
            "PayTraq rate limit hit (429). Wait a few seconds and retry; the server "
            "already throttles to 1 req/sec on average."
        )
    return PaytraqError(f"PayTraq request to '{path}' failed with HTTP {status}: {snippet}")


def _request(
    method: str,
    path: str,
    params: Optional[dict] = None,
    body: Optional[str] = None,
) -> dict:
    token, key = _credentials()
    merged_params = {"APIToken": token, "APIKey": key, **(params or {})}
    url = f"{BASE_URL}/{path.lstrip('/')}"
    headers = {"Content-Type": "application/xml; charset=utf-8"} if body else {}

    client = _get_client()
    body_bytes = body.encode("utf-8") if body else None

    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        _limiter.acquire()
        try:
            response = client.request(
                method=method,
                url=url,
                params=merged_params,
                content=body_bytes,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            raise PaytraqError(
                f"PayTraq request to '{path}' timed out after {DEFAULT_TIMEOUT_SECONDS}s "
                f"(tried {MAX_RETRIES} times). Try a smaller date range or retry later."
            ) from exc
        except httpx.RequestError as exc:
            raise PaytraqError(
                f"Network error talking to PayTraq ('{path}'): {exc}. "
                "Check connectivity to go.paytraq.com."
            ) from exc

        status = response.status_code

        if status == 429 and attempt < MAX_RETRIES - 1:
            wait = int(response.headers.get("Retry-After", "2"))
            time.sleep(max(1, wait))
            continue
        if status in (500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
            time.sleep(2 ** attempt)
            continue

        # PayTraq omits the charset in Content-Type; force UTF-8 so Latvian
        # diacritics (ī, ņ, ž, ā...) come through correctly.
        response.encoding = "utf-8"

        if status >= 400:
            raise _status_error(status, response.text, path)

        return parse_xml(response.text)

    # Exhausted retries without a raise — defensive.
    raise PaytraqError(
        f"PayTraq request to '{path}' failed after {MAX_RETRIES} retries: {last_error}"
    )


# ── Public request helpers ────────────────────────────────────────────────────

def get(path: str, params: Optional[dict] = None) -> dict:
    return _request("GET", path, params=params)


def post(path: str, data: dict, root_tag: str, params: Optional[dict] = None) -> dict:
    body = build_xml(root_tag, data)
    return _request("POST", path, params=params, body=body)


# ── Response formatting ───────────────────────────────────────────────────────

@dataclass
class ListResult:
    """Normalised listing with pagination metadata."""
    items: list
    page: int
    page_size: int
    count: int
    has_more: bool
    next_page: Optional[int]
    raw_container_tag: str


def _strip_envelope(parsed: dict) -> tuple[str, Any]:
    """From {RootTag: body} return (RootTag, body)."""
    if not isinstance(parsed, dict) or len(parsed) != 1:
        return "", parsed
    (root_tag, body) = next(iter(parsed.items()))
    return root_tag, body


def _extract_items(body: Any) -> list:
    """PayTraq wraps lists as {Root: {ItemTag: [...]}} or {Root: ""} when empty."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        if not body:
            return []
        # Prefer the singular child tag (e.g. Client inside Clients).
        for value in body.values():
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return [value]
        return []
    if body in ("", None):
        return []
    return [body]


def parse_list(parsed: dict, page: int) -> ListResult:
    """
    Interpret a PayTraq list response. PayTraq doesn't return a total count,
    so has_more is inferred from the page size (100 records/page). If the
    current page is full, a next page likely exists.
    """
    root_tag, body = _strip_envelope(parsed)
    items = _extract_items(body)
    count = len(items)
    has_more = count >= PAGE_SIZE
    return ListResult(
        items=items,
        page=page,
        page_size=PAGE_SIZE,
        count=count,
        has_more=has_more,
        next_page=(page + 1) if has_more else None,
        raw_container_tag=root_tag,
    )


def _truncate_json(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    marker = "\n...[truncated]..."
    return text[: limit - len(marker)] + marker, True


def format_single(parsed: dict, response_format: str = "json") -> str:
    """Format a single-entity response (get_*, create_*, update_*)."""
    if response_format == "markdown":
        return _to_markdown(parsed)
    body = json.dumps(parsed, ensure_ascii=False, indent=2)
    truncated, did_truncate = _truncate_json(body, CHARACTER_LIMIT)
    if did_truncate:
        truncated += (
            f"\n\n[response truncated at {CHARACTER_LIMIT} chars — "
            "request a specific field or narrower scope]"
        )
    return truncated


def format_list(result: ListResult, response_format: str = "json") -> str:
    """Format a list response with pagination metadata."""
    pagination = {
        "page": result.page,
        "page_size": result.page_size,
        "count": result.count,
        "has_more": result.has_more,
        "next_page": result.next_page,
    }

    if response_format == "markdown":
        return _list_to_markdown(result.raw_container_tag, result.items, pagination)

    # Shrink by dropping whole items so the output stays valid JSON.
    items = result.items
    truncated = False
    payload: dict[str, Any] = {"pagination": pagination, "items": items}
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    while len(body) > CHARACTER_LIMIT and len(items) > 1:
        items = items[: max(1, len(items) // 2)]
        truncated = True
        payload = {
            "pagination": {**pagination, "truncated_to": len(items)},
            "items": items,
        }
        body = json.dumps(payload, ensure_ascii=False, indent=2)
    if truncated:
        hint = (
            f"\n\n[response shrunk from {result.count} to {len(items)} items "
            f"to fit {CHARACTER_LIMIT}-char limit — request a narrower filter "
            f"or call again with page={result.next_page or result.page + 1}]"
        )
        body += hint
    return body


def format_raw(parsed: dict, response_format: str = "json") -> str:
    """Pass-through for endpoints that don't fit the single/list pattern."""
    return format_single(parsed, response_format)


# ── Markdown helpers (lightweight; JSON is the canonical form) ────────────────

def _to_markdown(parsed: dict, level: int = 1) -> str:
    lines: list[str] = []
    _render_markdown(parsed, lines, level)
    rendered = "\n".join(lines).rstrip()
    if len(rendered) > CHARACTER_LIMIT:
        rendered = rendered[:CHARACTER_LIMIT] + "\n\n[response truncated]"
    return rendered or "_(empty response)_"


def _render_markdown(value: Any, lines: list[str], level: int) -> None:
    prefix = "#" * min(level, 6)
    if isinstance(value, dict):
        for key, sub in value.items():
            if isinstance(sub, (dict, list)) and sub:
                lines.append(f"\n{prefix} {key}")
                _render_markdown(sub, lines, level + 1)
            else:
                lines.append(f"- **{key}**: {_scalar(sub)}")
    elif isinstance(value, list):
        for i, item in enumerate(value, 1):
            lines.append(f"\n{prefix} Item {i}")
            _render_markdown(item, lines, level + 1)
    else:
        lines.append(_scalar(value))


def _scalar(value: Any) -> str:
    if value is None or value == "":
        return "_(empty)_"
    return str(value)


def _list_to_markdown(container: str, items: Iterable[dict], pagination: dict) -> str:
    lines = [f"# {container or 'Results'}"]
    lines.append(
        f"_page {pagination['page']} · {pagination['count']} item(s)_"
        + (f" · next page: {pagination['next_page']}" if pagination["has_more"] else "")
    )
    for idx, item in enumerate(items, 1):
        lines.append(f"\n## {idx}.")
        _render_markdown(item, lines, 3)
    rendered = "\n".join(lines).rstrip()
    if len(rendered) > CHARACTER_LIMIT:
        rendered = rendered[:CHARACTER_LIMIT] + "\n\n[response truncated]"
    return rendered
