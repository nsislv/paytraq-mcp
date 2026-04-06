"""
PayTraq MCP — Accounting Tools
---------------------------------
Tools for accessing the chart of accounts, tax keys, and journal entries.

When to use these tools:
  - list_accounts / get_account: look up account codes and IDs for reporting
    or when manually creating journal entries
  - list_tax_keys: find the correct VAT/tax code before creating products
    or services
  - list_journals: review journal entries for a period (useful for audits
    and reconciliation)
"""

import re
from typing import Annotated, Optional
from pydantic import Field
from mcp.server.fastmcp import FastMCP
from paytraq_client import get, format_response

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(value: Optional[str], field_name: str) -> Optional[str]:
    if value and not _DATE_RE.match(value):
        return f"Invalid {field_name} format '{value}'. Use YYYY-MM-DD (e.g. 2026-01-01)."
    return None


def register(mcp: FastMCP) -> None:

    # ── CHART OF ACCOUNTS ─────────────────────────────────────────────────────

    @mcp.tool()
    def list_accounts(
        query: Annotated[Optional[str], Field(
            default=None,
            description="Search by account name or account number/code.",
        )] = None,
    ) -> str:
        """
        List all accounts in the PayTraq chart of accounts (COA).

        Use this tool when you need to:
        - Find account IDs or codes for financial reports
        - Look up which account number corresponds to a P&L or balance sheet line
        - Verify account names and types before creating journal entries
        """
        try:
            params: dict = {}
            if query:
                params["query"] = query
            return format_response(get("accounts", params if params else None))
        except Exception as e:
            raise

    @mcp.tool()
    def get_account(
        account_id: Annotated[int, Field(
            description="Numeric PayTraq account ID from the chart of accounts.",
            gt=0,
        )],
    ) -> str:
        """
        Get details of a specific account from the chart of accounts.

        Use this tool when you need the full definition of an account (name,
        code, type DR/CR, group) before using it in a report or journal entry.
        """
        try:
            return format_response(get(f"account/{account_id}"))
        except Exception as e:
            raise

    # ── TAX KEYS ──────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_tax_keys() -> str:
        """
        List all tax keys (VAT rates and other tax codes) configured in PayTraq.

        Use this tool before creating products, services, or documents when
        you need to select the correct tax/VAT rate code (e.g. standard 21%,
        reduced 12%, zero-rated, exempt).
        """
        try:
            return format_response(get("taxkeys"))
        except Exception as e:
            raise

    # ── JOURNALS ──────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_journals(
        date_from: Annotated[Optional[str], Field(
            default=None,
            description="Start date for journal entries in YYYY-MM-DD format.",
        )] = None,
        date_till: Annotated[Optional[str], Field(
            default=None,
            description="End date for journal entries in YYYY-MM-DD format.",
        )] = None,
        page: Annotated[int, Field(
            default=0,
            ge=0,
            description="Page number for pagination (100 records per page).",
        )] = 0,
    ) -> str:
        """
        List journal entries (double-entry bookkeeping records) for a period.

        Use this tool when you need to:
        - Audit accounting entries for a specific date range
        - Reconcile posted transactions with source documents
        - Review debit/credit postings before generating financial reports
        Note: The profit_and_loss and balance_sheet report tools call this
        internally — use this tool only when you need the raw journal data.
        """
        try:
            for val, name in [(date_from, "date_from"), (date_till, "date_till")]:
                err = _validate_date(val, name)
                if err:
                    return f"Error: {err}"

            params: dict = {"page": page}
            if date_from: params["date_from"] = date_from
            if date_till: params["date_till"] = date_till
            return format_response(get("journals", params))
        except Exception as e:
            raise
