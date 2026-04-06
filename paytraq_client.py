"""
PayTraq API Client
------------------
Base HTTP client with:
- Rate limiting (1 req/sec avg, burst 5, max 5000/day)
- Automatic XML parsing
- Retry on 429/5xx errors
- Centralised error handling
"""

import os
import time
import threading
import xml.etree.ElementTree as ET
from typing import Optional, Any
from datetime import datetime, timezone

UTC = timezone.utc

import httpx

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_URL = "https://go.paytraq.com/api"

API_TOKEN = os.getenv("PAYTRAQ_API_TOKEN", "")
API_KEY = os.getenv("PAYTRAQ_API_KEY", "")


# ── Rate Limiter ──────────────────────────────────────────────────────────────

class RateLimiter:
    """
    Token-bucket rate limiter.
    PayTraq: 1 req/sec avg, burst up to 5, 5000 req/day max.
    """

    def __init__(self, rate: float = 1.0, burst: int = 5):
        self.rate = rate          # tokens per second
        self.burst = burst        # max tokens
        self.tokens = burst       # current tokens
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

        # Daily counter
        self.daily_count = 0
        self.daily_limit = 5000
        self.daily_reset = datetime.now(UTC).date()

    def acquire(self) -> None:
        with self._lock:
            # Reset daily counter on new day
            today = datetime.now(UTC).date()
            if today != self.daily_reset:
                self.daily_count = 0
                self.daily_reset = today

            if self.daily_count >= self.daily_limit:
                raise RuntimeError(
                    f"PayTraq daily limit reached ({self.daily_limit} requests). "
                    "Resets at midnight UTC."
                )

            # Refill tokens
            now = time.monotonic()
            elapsed = now - self.last_refill
            refill = elapsed * self.rate
            self.tokens = min(self.burst, self.tokens + refill)
            self.last_refill = now

            # Wait if no tokens available
            if self.tokens < 1:
                wait = (1 - self.tokens) / self.rate
                time.sleep(wait)
                self.tokens = 0
            else:
                self.tokens -= 1

            self.daily_count += 1


_limiter = RateLimiter()


# ── XML Helpers ───────────────────────────────────────────────────────────────

def xml_to_dict(element: ET.Element) -> Any:
    """Recursively converts an XML Element to a dict or str."""
    children = list(element)
    if not children:
        return element.text or ""

    result = {}
    for child in children:
        value = xml_to_dict(child)
        if child.tag in result:
            # Convert to list on duplicate tags
            existing = result[child.tag]
            if not isinstance(existing, list):
                result[child.tag] = [existing]
            result[child.tag].append(value)
        else:
            result[child.tag] = value
    return result


def parse_xml(text: str) -> dict:
    """Parses a PayTraq XML response into a dict."""
    try:
        root = ET.fromstring(text)
        return {root.tag: xml_to_dict(root)}
    except ET.ParseError as e:
        return {"parse_error": str(e), "raw": text[:500]}


def build_xml(tag: str, data: dict) -> str:
    """Builds an XML string from a dict for POST requests."""
    def _build(parent: ET.Element, d: dict) -> None:
        for key, val in d.items():
            child = ET.SubElement(parent, key)
            if isinstance(val, dict):
                _build(child, val)
            elif val is not None:
                child.text = str(val)

    root = ET.Element(tag)
    _build(root, data)
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


# ── Core Request ──────────────────────────────────────────────────────────────

def _request(
    method: str,
    path: str,
    params: Optional[dict] = None,
    body: Optional[str] = None,
    retries: int = 3,
) -> dict:
    """
    Executes an HTTP request to the PayTraq API.
    Automatically appends auth parameters and respects the rate limit.
    """
    if not API_TOKEN or not API_KEY:
        return {"error": "PAYTRAQ_API_TOKEN and PAYTRAQ_API_KEY must be set."}

    auth_params = {"APIToken": API_TOKEN, "APIKey": API_KEY}
    all_params = {**auth_params, **(params or {})}

    url = f"{BASE_URL}/{path.lstrip('/')}"
    headers = {"Content-Type": "application/xml"} if body else {}

    for attempt in range(retries):
        _limiter.acquire()
        try:
            with httpx.Client(timeout=30) as client:
                response = client.request(
                    method=method,
                    url=url,
                    params=all_params,
                    content=body,
                    headers=headers,
                )

            # Error handling
            if response.status_code == 429:
                wait = int(response.headers.get("Retry-After", 60))
                time.sleep(wait)
                continue
            if response.status_code in (500, 501, 503):
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return {"error": f"Server error {response.status_code}", "raw": response.text[:300]}
            if response.status_code == 401:
                return {"error": "Unauthorized: check PAYTRAQ_API_TOKEN and PAYTRAQ_API_KEY"}
            if response.status_code == 403:
                return {"error": "Forbidden: insufficient permissions"}
            if response.status_code == 404:
                return {"error": f"Not found: {path}"}
            if response.status_code == 400:
                return {"error": f"Bad request: {response.text[:300]}"}

            response.raise_for_status()
            return parse_xml(response.text)

        except httpx.TimeoutException:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            return {"error": "Request timed out after 30s"}
        except Exception as e:
            return {"error": str(e)}

    return {"error": "Max retries exceeded"}


# ── Public API ────────────────────────────────────────────────────────────────

def get(path: str, params: Optional[dict] = None) -> dict:
    return _request("GET", path, params=params)


def post(path: str, data: dict, root_tag: str, params: Optional[dict] = None) -> dict:
    body = build_xml(root_tag, data)
    return _request("POST", path, params=params, body=body)


def format_response(data: dict, max_items: int = 50) -> str:
    """
    Formats a dict response into a readable string for MCP tools.
    Raises RuntimeError on API errors so FastMCP returns isError:true.
    Truncates large result sets and includes pagination guidance.
    """
    import json

    if "error" in data:
        raise RuntimeError(data['error'])

    # Count top-level items
    def _count_items(d: Any, depth: int = 0) -> int:
        if isinstance(d, list):
            return len(d)
        if isinstance(d, dict) and depth == 0:
            for v in d.values():
                return _count_items(v, depth + 1)
        return 1

    total = _count_items(data)
    if total > max_items:
        # Show only the first max_items
        data = _truncate(data, max_items)
        result = json.dumps(data, ensure_ascii=False, indent=2)
        return (
            f"{result}\n\n"
            f"⚠️  Results truncated: showing first {max_items} of {total} items. "
            f"Pass page=1, page=2, ... to retrieve the next pages (100 records each)."
        )

    return json.dumps(data, ensure_ascii=False, indent=2)


def _truncate(data: Any, limit: int) -> Any:
    if isinstance(data, list):
        return data[:limit]
    if isinstance(data, dict):
        return {k: _truncate(v, limit) for k, v in data.items()}
    return data
