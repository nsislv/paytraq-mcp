"""
PayTraq MCP Server
------------------
Model Context Protocol server for the PayTraq cloud ERP / accounting system.

Capabilities:
  - Clients, suppliers, employees (CRUD + contacts / banks / groups)
  - Sales & purchase document lifecycle (create → approve → post → pay / void)
  - Payments, attachments, PDFs
  - Products, services, warehouses, inventory, lots, shippers
  - Chart of accounts, tax keys, journals
  - Financial reports (P&L, balance sheet, quarterly)

Required environment variables:
  PAYTRAQ_API_TOKEN  — token issued in PayTraq → Settings → API
  PAYTRAQ_API_KEY    — API key issued in PayTraq → Settings → API

Usage (stdio transport for MCP clients like Claude Desktop):
  PAYTRAQ_API_TOKEN=xxx PAYTRAQ_API_KEY=yyy python server.py

PayTraq rate limits (enforced client-side automatically):
  1 req/sec avg, burst of 5, 5000 req/day. The server throttles and retries
  on 429 / 5xx; long reports may take time because of this.
"""

from __future__ import annotations

import atexit
import os
import sys

from mcp.server.fastmcp import FastMCP

import paytraq_client
from tools import accounting, clients, documents, products, reports


INSTRUCTIONS = (
    "You are connected to PayTraq, a cloud accounting & ERP system. "
    "Capabilities: clients/suppliers/employees, sales & purchase documents "
    "(draft → approved → posted → paid/voided), payments, products/services, "
    "warehouses & inventory, chart of accounts, tax keys, journals, and P&L / "
    "balance-sheet reports.\n\n"
    "Conventions:\n"
    "- Every tool name is prefixed 'paytraq_' to avoid collisions with other MCP servers.\n"
    "- Dates use YYYY-MM-DD. Decimals use a dot (10.90). Country codes are ISO "
    "  3166-1 alpha-2 (LV, EE, DE). Currency codes are ISO 4217 (EUR, USD).\n"
    "- List tools support pagination (page=0,1,...) and return has_more / "
    "  next_page. 100 records per page.\n"
    "- All tools accept response_format='json' (default) or 'markdown'.\n"
    "- Read-only tools are hinted as such via MCP annotations; destructive "
    "  actions (void_sale) are hinted destructive.\n"
    "- The API is throttled to ~1 req/sec — expect short waits on large queries."
)


def _require_env() -> None:
    token = os.environ.get("PAYTRAQ_API_TOKEN", "").strip()
    key = os.environ.get("PAYTRAQ_API_KEY", "").strip()
    if not token or not key:
        print(
            "ERROR: PAYTRAQ_API_TOKEN and PAYTRAQ_API_KEY environment variables are required.\n"
            "  Find them in PayTraq -> Settings -> API and set them before starting.\n"
            "  Example:\n"
            "    PAYTRAQ_API_TOKEN=xxx PAYTRAQ_API_KEY=yyy python server.py",
            file=sys.stderr,
        )
        sys.exit(1)


def build_server() -> FastMCP:
    """Construct and wire up the FastMCP server."""
    mcp = FastMCP("paytraq-mcp", instructions=INSTRUCTIONS)
    accounting.register(mcp)
    clients.register(mcp)
    documents.register(mcp)
    products.register(mcp)
    reports.register(mcp)
    return mcp


def main() -> None:
    _require_env()
    atexit.register(paytraq_client.close)
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
