"""
PayTraq MCP — Accounting Tools
--------------------------------
Инструменты для работы с бухгалтерией:
- План счетов
- Налоговые ключи
- Журнальные проводки
"""

from typing import Optional
from mcp.server.fastmcp import FastMCP
from paytraq_client import get, format_response


def register(mcp: FastMCP) -> None:

    # ── CHART OF ACCOUNTS ─────────────────────────────────────────────────────

    @mcp.tool()
    def list_accounts(query: Optional[str] = None) -> str:
        """
        Получить план счетов (chart of accounts).

        Args:
            query: Поиск по названию или номеру счёта
        """
        params: dict = {}
        if query: params["query"] = query
        return format_response(get("accounts", params if params else None))

    @mcp.tool()
    def get_account(account_id: int) -> str:
        """
        Получить информацию о счёте по ID.

        Args:
            account_id: ID счёта
        """
        return format_response(get(f"account/{account_id}"))

    # ── TAX KEYS ──────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_tax_keys() -> str:
        """
        Получить список налоговых ключей (ставки НДС и других налогов).
        Используются при создании товаров, услуг и документов.
        """
        return format_response(get("taxkeys"))

    # ── JOURNALS ──────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_journals(
        date_from: Optional[str] = None,
        date_till: Optional[str] = None,
        page: int = 0,
    ) -> str:
        """
        Получить журнальные проводки (journal entries).

        Args:
            date_from: Дата начала YYYY-MM-DD
            date_till: Дата конца YYYY-MM-DD
            page:      Страница (по умолчанию 0)
        """
        params: dict = {"page": page}
        if date_from: params["date_from"] = date_from
        if date_till: params["date_till"] = date_till
        return format_response(get("journals", params))
