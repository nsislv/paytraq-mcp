"""
PayTraq MCP — Accounting tools.

Read-only lookups for the chart of accounts, tax keys, and journal entries.
These are the building blocks for financial reporting and manual postings.
"""

from __future__ import annotations

from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from paytraq_client import format_list, format_single, get, parse_list
from tools._common import ResponseFormat, ensure_date


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="paytraq_list_accounts",
        title="List chart-of-accounts entries",
        annotations=READ_ONLY,
    )
    def paytraq_list_accounts(
        query: Annotated[Optional[str], Field(
            description="Optional search by account name or code (e.g. '6110', 'Revenue').",
        )] = None,
        page: Annotated[int, Field(
            ge=0,
            description="0-indexed page number (100 records per page).",
        )] = 0,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' for structured data (default) or 'markdown' for human-readable.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        List accounts in the PayTraq chart of accounts (COA).

        Use this to:
          - Find account IDs or codes for journal entries and reporting.
          - Look up which account number corresponds to a P&L / balance-sheet line.
          - Verify account names and DR/CR types before posting.

        Returns a paginated list with has_more / next_page metadata.
        """
        params: dict = {"page": page}
        if query:
            params["query"] = query
        parsed = get("accounts", params)
        result = parse_list(parsed, page=page)
        return format_list(result, response_format.value)

    @mcp.tool(
        name="paytraq_get_account",
        title="Get a single chart-of-accounts entry",
        annotations=READ_ONLY,
    )
    def paytraq_get_account(
        account_id: Annotated[int, Field(
            gt=0,
            description="Numeric PayTraq account ID (from paytraq_list_accounts).",
        )],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        Return the full definition of one account (name, code, DR/CR type, group).

        Use before generating a journal entry or when you need to understand an
        account referenced in a report line.
        """
        parsed = get(f"account/{account_id}")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_list_tax_keys",
        title="List VAT / tax keys",
        annotations=READ_ONLY,
    )
    def paytraq_list_tax_keys(
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        List every configured tax key (VAT rates, reverse-charge, zero-rated, exempt).

        Call this first whenever you're about to create a product, service, or
        document — the PayTraq API requires a valid TaxKeyID.
        """
        # NOTE: endpoint is camelCase taxKeys — lowercase 'taxkeys' 404s.
        parsed = get("taxKeys")
        result = parse_list(parsed, page=0)
        return format_list(result, response_format.value)

    @mcp.tool(
        name="paytraq_list_journals",
        title="List general-ledger journal entries",
        annotations=READ_ONLY,
    )
    def paytraq_list_journals(
        date_from: Annotated[Optional[str], Field(
            description="Start date (YYYY-MM-DD). Omit to accept the PayTraq default (current year).",
        )] = None,
        date_till: Annotated[Optional[str], Field(
            description="End date (YYYY-MM-DD) inclusive.",
        )] = None,
        page: Annotated[int, Field(
            ge=0,
            description="0-indexed page number (100 records per page).",
        )] = 0,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        List posted journal entries (double-entry bookkeeping records) for a period.

        Use this to:
          - Audit accounting entries for a date range.
          - Reconcile posted transactions with their source documents.
          - Extract raw DR/CR data when paytraq_profit_and_loss or
            paytraq_balance_sheet doesn't give you the level of detail you need.
        """
        ensure_date(date_from, "date_from")
        ensure_date(date_till, "date_till")

        params: dict = {"page": page}
        if date_from:
            params["date_from"] = date_from
        if date_till:
            params["date_till"] = date_till
        parsed = get("journals", params)
        result = parse_list(parsed, page=page)
        return format_list(result, response_format.value)
