"""
PayTraq MCP Server
------------------
MCP-сервер для интеграции с PayTraq — облачной системой учёта.

Покрывает полный API v2.57:
  • Клиенты, поставщики, сотрудники
  • Документы продаж и закупок, платежи
  • Товары, услуги, склад, инвентарь
  • Бухгалтерия, налоги, журналы

Требования:
  PAYTRAQ_API_TOKEN — токен из настроек PayTraq
  PAYTRAQ_API_KEY   — ключ API из настроек PayTraq

Запуск:
  PAYTRAQ_API_TOKEN=xxx PAYTRAQ_API_KEY=yyy python server.py

Rate limits (соблюдаются автоматически):
  1 запрос/сек avg | burst 5 | 5000 запросов/сутки
"""

import os
import sys
from mcp.server.fastmcp import FastMCP

# ── Проверка переменных окружения ─────────────────────────────────────────────

_TOKEN = os.getenv("PAYTRAQ_API_TOKEN", "")
_KEY   = os.getenv("PAYTRAQ_API_KEY", "")

if not _TOKEN or not _KEY:
    print(
        "❌ ERROR: Set PAYTRAQ_API_TOKEN and PAYTRAQ_API_KEY environment variables.\n"
        "  Example:\n"
        "    export PAYTRAQ_API_TOKEN=your_token\n"
        "    export PAYTRAQ_API_KEY=your_key\n",
        file=sys.stderr,
    )
    sys.exit(1)

# ── Инициализация MCP ─────────────────────────────────────────────────────────

mcp = FastMCP(
    "PayTraq",
    instructions=(
        "You are connected to PayTraq — a cloud-based accounting and ERP system. "
        "You can manage clients, suppliers, employees, products, services, "
        "sales invoices, purchase orders, payments, inventory, and accounting records. "
        "All monetary values use dot as decimal separator (e.g. 10.90). "
        "Dates must be in YYYY-MM-DD format. "
        "Country codes are 2-letter ISO (LV, EE, LT, DE...). "
        "Currency codes follow ISO 4217 (EUR, USD, GBP...). "
        "The API is rate-limited to 1 req/sec on average — responses may take a moment."
    ),
)

# ── Регистрация инструментов ──────────────────────────────────────────────────

from tools import clients, documents, products, accounting, reports

clients.register(mcp)
documents.register(mcp)
products.register(mcp)
accounting.register(mcp)
reports.register(mcp)

# ── Запуск ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
