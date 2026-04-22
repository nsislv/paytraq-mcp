"""
Shared validators and enums used across all PayTraq tools.

All input validation that fails must raise PaytraqBadRequest so FastMCP
reports isError=True with a clear, actionable message.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from paytraq_client import PaytraqBadRequest

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class ResponseFormat(str, Enum):
    """Output format hint for all listing / detail tools."""
    JSON = "json"
    MARKDOWN = "markdown"


def ensure_date(value: Optional[str], field: str) -> Optional[str]:
    """Return the date unchanged, or raise with a targeted error message."""
    if value is None or value == "":
        return None
    if not _DATE_RE.match(value):
        raise PaytraqBadRequest(
            f"Invalid {field}='{value}'. Use YYYY-MM-DD (e.g. 2026-01-31)."
        )
    return value


def ensure_email(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return None
    if not _EMAIL_RE.match(value):
        raise PaytraqBadRequest(
            f"Invalid email '{value}'. Expected format: local@domain.tld"
        )
    return value


def ensure_country(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return None
    upper = value.upper()
    if not _COUNTRY_RE.match(upper):
        raise PaytraqBadRequest(
            f"Invalid country '{value}'. Use 2-letter ISO 3166-1 alpha-2 (e.g. LV, EE, LT, DE)."
        )
    return upper


def ensure_currency(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return None
    upper = value.upper()
    if not _CURRENCY_RE.match(upper):
        raise PaytraqBadRequest(
            f"Invalid currency '{value}'. Use 3-letter ISO 4217 (e.g. EUR, USD, GBP)."
        )
    return upper


def ensure_in(value: Optional[str], allowed: set[str], field: str) -> Optional[str]:
    if value is None or value == "":
        return None
    if value not in allowed:
        raise PaytraqBadRequest(
            f"Invalid {field}='{value}'. Allowed values: {', '.join(sorted(allowed))}."
        )
    return value


def drop_none(data: dict) -> dict:
    """Remove keys whose value is None or empty string — PayTraq dislikes empty tags."""
    return {k: v for k, v in data.items() if v is not None and v != ""}
