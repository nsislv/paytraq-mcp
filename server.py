"""
PayTraq MCP Server
------------------
MCP server for integrating with PayTraq — a cloud-based accounting and ERP system.

Covers the full API v2.57:
  • Clients, suppliers, employees
  • Sales and purchase documents, payments
  • Products, services, warehouse, inventory
  • Accounting, taxes, journals, financial reports

Requirements:
  PAYTRAQ_API_TOKEN — token from PayTraq settings
  PAYTRAQ_API_KEY   — API key from PayTraq settings

Usage:
  PAYTRAQ_API_TOKEN=xxx PAYTRAQ_API_KEY=yyy python server.py

Rate limits (enforced automatically):
  1 req/sec avg | burst 5 | 5000 requests/day
"""

import os
import sys
from mcp.server.fastmcp import FastMCP

# ── Environment variable check ────────────────────────────────────────────────

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

# ── MCP initialisation ────────────────────────────────────────────────────────

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

# ── Tool registration ─────────────────────────────────────────────────────────

from tools import clients, documents, products, accounting, reports

clients.register(mcp)
documents.register(mcp)
products.register(mcp)
accounting.register(mcp)
reports.register(mcp)

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
