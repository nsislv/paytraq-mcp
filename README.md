# PayTraq MCP

[Model Context Protocol](https://modelcontextprotocol.io/) server for
[PayTraq](https://paytraq.com) — a cloud-based accounting and ERP system.
Lets Claude Desktop and other MCP clients drive PayTraq through natural
language: manage clients and suppliers, issue and post invoices, record
payments, check inventory, and run financial reports.

---

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running](#running)
- [Claude Desktop integration](#claude-desktop-integration)
- [Available tools](#available-tools)
- [Response formats](#response-formats)
- [Pagination](#pagination)
- [Rate limits and retries](#rate-limits-and-retries)
- [Project structure](#project-structure)
- [Data formats](#data-formats)

---

## Requirements

- Python 3.10+
- A PayTraq account with API access
- `PAYTRAQ_API_TOKEN` and `PAYTRAQ_API_KEY` (PayTraq → Settings → API)

---

## Installation

```bash
git clone https://github.com/nsislv/Paytraq-mcp.git
cd paytraq-mcp

python -m venv venv
source venv/bin/activate        # Linux / macOS
# venv\Scripts\activate.bat     # Windows

pip install -r requirements.txt
```

---

## Configuration

Set the two environment variables before starting the server:

```bash
export PAYTRAQ_API_TOKEN=your_token
export PAYTRAQ_API_KEY=your_key
```

Credentials are found in **PayTraq → Settings → API**. The server reads them
at request time, so rotating keys without a restart is safe.

---

## Running

```bash
python server.py
```

The server communicates over stdio and exposes all tools listed below.

---

## Claude Desktop integration

The Claude Desktop config file lives at:

| OS | Path |
|----|------|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS   | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux   | `~/.config/Claude/claude_desktop_config.json` |

Add a `mcpServers` entry (keep any other top-level keys the file already has):

```json
{
  "mcpServers": {
    "paytraq": {
      "command": "python",
      "args": ["/absolute/path/to/paytraq-mcp/server.py"],
      "env": {
        "PAYTRAQ_API_TOKEN": "your_token",
        "PAYTRAQ_API_KEY": "your_key"
      }
    }
  }
}
```

**Windows example** (backslashes must be escaped in JSON):

```json
{
  "mcpServers": {
    "paytraq": {
      "command": "C:\\Python\\python.exe",
      "args": ["C:\\Users\\you\\Projects\\paytraq-mcp\\server.py"],
      "env": {
        "PAYTRAQ_API_TOKEN": "your_token",
        "PAYTRAQ_API_KEY": "your_key"
      }
    }
  }
}
```

Restart Claude Desktop. The PayTraq tools appear in the 🔌 menu; in a new
conversation ask "list my PayTraq clients" to verify the connection.

### Troubleshooting

- **"Server disconnected" in the Claude Desktop log**: the Python process
  exited on start — usually missing env vars. Check
  `%APPDATA%\Claude\logs\mcp-server-paytraq.log`.
- **Tools don't show up**: use an absolute path to `python` (not just `python`)
  and an absolute path to `server.py`. Relative paths are resolved against an
  unpredictable working directory.
- **Latvian / Baltic characters look mangled**: that's a display issue in the
  client, not the server — the server sends UTF-8 correctly. Update to a
  recent Claude Desktop build if it persists.
- **401 Unauthorized in responses**: regenerate `PAYTRAQ_API_TOKEN` and
  `PAYTRAQ_API_KEY` in PayTraq → Settings → API and update the config.

---

## Available tools

**64 tools** across 5 modules. Every tool name is prefixed `paytraq_` so it
cannot collide with tools from other MCP servers. Every tool carries MCP
annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`,
`openWorldHint`) so clients can present the right confirmations.

### Clients, suppliers & employees — `tools/clients.py`

| Tool | Read-only | Description |
|------|:---------:|-------------|
| `paytraq_list_clients` | ✓ | List clients with search and pagination |
| `paytraq_get_client` | ✓ | Get a client by ID |
| `paytraq_create_client` |   | Create a new client |
| `paytraq_update_client` |   | Update client fields |
| `paytraq_get_client_outstanding` | ✓ | Unpaid invoices + outstanding balance |
| `paytraq_list_client_contacts` | ✓ | List contact persons |
| `paytraq_add_client_contact` |   | Add a contact person |
| `paytraq_list_client_banks` | ✓ | Client bank account details |
| `paytraq_list_client_groups` | ✓ | List client groups |
| `paytraq_list_suppliers` | ✓ | List suppliers |
| `paytraq_get_supplier` | ✓ | Get supplier by ID |
| `paytraq_create_supplier` |   | Create a supplier |
| `paytraq_update_supplier` |   | Update supplier fields |
| `paytraq_list_supplier_groups` | ✓ | List supplier groups |
| `paytraq_list_employees` | ✓ | List employees |
| `paytraq_get_employee` | ✓ | Get employee by ID |
| `paytraq_create_employee` |   | Create an employee |
| `paytraq_list_employee_groups` | ✓ | List employee groups |

### Sales, purchases & payments — `tools/documents.py`

| Tool | Read-only | Description |
|------|:---------:|-------------|
| `paytraq_list_sales` | ✓ | List sales documents (status / date / client filters, `unpaid_only`) |
| `paytraq_get_sale` | ✓ | Full invoice/order details |
| `paytraq_create_sale` |   | Create a sales document |
| `paytraq_approve_sale` |   | Move draft → approved |
| `paytraq_post_sale` |   | Post to the accounting ledger |
| `paytraq_void_sale` |   | **Destructive** — cancel a document |
| `paytraq_record_sale_payment` |   | Record a customer payment |
| `paytraq_send_sale` |   | Email the document to the client |
| `paytraq_get_sale_pdf` | ✓ | Get PDF download data |
| `paytraq_list_purchases` | ✓ | List purchase documents (status / date / supplier filters, `unpaid_only`) |
| `paytraq_get_purchase` | ✓ | Full purchase document details |
| `paytraq_create_purchase` |   | Create a purchase document |
| `paytraq_approve_purchase` |   | Move draft → approved |
| `paytraq_post_purchase` |   | Post to the ledger |
| `paytraq_record_purchase_payment` |   | Record payment to a supplier |
| `paytraq_list_payments` | ✓ | List all payment records |
| `paytraq_get_payment` | ✓ | Get payment details |
| `paytraq_list_attachments` | ✓ | List document attachments |

**Sales document types (`sale_type`):**
`sales_invoice`, `sales_order`, `sales_proforma`, `sales_receipt`, `credit_note`

**Statuses (`status`):** `draft`, `approved`, `posted`, `wait_payment`, `paid`, `voided`

> PayTraq's `status` filter is imprecise for finding outstanding balances —
> it can return fully-paid documents and miss genuinely unpaid ones. For a
> reliable "show me everything that still owes money" query use the
> **`unpaid_only=True`** flag on `paytraq_list_sales` / `paytraq_list_purchases`
> instead. It filters client-side on `AmountDue > 0`, which always matches
> the actual receivable/payable balance.

**Ordering (`reverse`):** PayTraq's natural order is **newest-first**
(descending by DocumentDate). Set `reverse=True` to flip to oldest-first.

**Line items** are passed as a list of dicts:

```json
[
  {"ItemID": 42, "Qty": 2, "Price": 150.00},
  {"ItemID": 99, "Qty": 1, "Price": 49.50}
]
```

### Products, services & warehouse — `tools/products.py`

| Tool | Read-only | Description |
|------|:---------:|-------------|
| `paytraq_list_products` | ✓ | Search by name / SKU / barcode |
| `paytraq_get_product` | ✓ | Full product details |
| `paytraq_create_product` |   | Create a product |
| `paytraq_update_product` |   | Update product fields |
| `paytraq_get_product_price_list` | ✓ | Prices for one price group |
| `paytraq_set_product_price` |   | Set a product price |
| `paytraq_list_product_groups` | ✓ | List product groups |
| `paytraq_list_lots` | ✓ | List lots / batches |
| `paytraq_add_product_lot` |   | Add a lot with expiry date |
| `paytraq_list_services` | ✓ | List services |
| `paytraq_get_service` | ✓ | Get service by ID |
| `paytraq_create_service` |   | Create a service item |
| `paytraq_update_service` |   | Update service fields |
| `paytraq_list_service_groups` | ✓ | List service groups |
| `paytraq_list_warehouses` | ✓ | List warehouses |
| `paytraq_get_warehouse` | ✓ | Warehouse details |
| `paytraq_get_current_inventory` | ✓ | Current stock at a warehouse |
| `paytraq_get_product_inventory` | ✓ | One product's stock across warehouses |
| `paytraq_list_loading_areas` | ✓ | List loading / unloading areas |
| `paytraq_list_shippers` | ✓ | List shipping carriers |
| `paytraq_create_shipper` |   | Register a shipping carrier |

**Product types:** `1` = storable, `2` = consumable, `3` = fixed asset.

### Accounting — `tools/accounting.py`

| Tool | Read-only | Description |
|------|:---------:|-------------|
| `paytraq_list_accounts` | ✓ | Chart of accounts, searchable |
| `paytraq_get_account` | ✓ | Account by ID |
| `paytraq_list_tax_keys` | ✓ | VAT / tax keys |
| `paytraq_list_journals` | ✓ | Journal entries with date filter |

### Financial reports — `tools/reports.py`

| Tool | Read-only | Description |
|------|:---------:|-------------|
| `paytraq_profit_and_loss` | ✓ | P&L / income statement for any date range |
| `paytraq_balance_sheet` | ✓ | Balance sheet snapshot as of a given date |
| `paytraq_quarterly_report` | ✓ | Combined P&L + balance sheet for one quarter |

> **Note:** Reports are computed by aggregating general-ledger journal entries.
> Figures may differ slightly from PayTraq's PDF reports, which use the
> sub-ledger. PayTraq v2.57 does not expose an account-balance endpoint.

---

## Response formats

Every list / detail / report tool accepts `response_format`:

- **`json`** (default for CRUD tools) — structured, machine-readable. Lists
  include a `pagination` block; reports include per-section totals and subtotals.
- **`markdown`** (default for reports) — human-readable with headers and
  aligned columns; ideal for chat output.

---

## Pagination

List tools return a pagination block:

```json
{
  "pagination": {
    "page": 0,
    "page_size": 100,
    "count": 100,
    "has_more": true,
    "next_page": 1
  },
  "items": [...]
}
```

PayTraq does not expose a `total_count`, so `has_more` is inferred from page
fullness (100 records/page). Pass `page=1`, `page=2`, ... to walk pages.

### Response size limit

All responses are capped at **25 000 characters** to stay within MCP client
context budgets. When a list page is too large, items are dropped from the
tail of the payload (not the API) and a `truncated_to: N` note is added to
`pagination`, plus a trailing message:

```
[response shrunk from 100 to 12 items to fit 25000-char limit
 — request a narrower filter or call again with page=1]
```

**Important:** the trimmed items still exist in PayTraq — they were only
removed from this page's payload. To see them, either:

- narrow the query (`date_from` / `date_till` / `client_id` / `unpaid_only`),
  or
- request the next page.

---

## Rate limits and retries

Built-in limits are enforced **automatically**:

| Parameter | Value |
|-----------|-------|
| Average rate | 1 req/sec |
| Burst | up to 5 requests |
| Daily quota | 5 000 requests (resets at 00:00 UTC) |
| Per-request timeout | 30 s |
| Page size | 100 records |

On 429 / 500 / 502 / 503 / 504 the client retries with exponential back-off (up to 3 attempts).
On 401 / 403 / 404 / 400 the tool fails fast with an actionable error that
tells the LLM what to fix.

---

## Project structure

```
paytraq-mcp/
├── server.py              # MCP entry point (FastMCP, stdio transport)
├── paytraq_client.py      # HTTP client: rate limit, retries, XML <-> dict,
│                          # list pagination, json/markdown formatters
├── requirements.txt
└── tools/
    ├── __init__.py
    ├── _common.py         # Shared validators and ResponseFormat enum
    ├── accounting.py      # Accounts, tax keys, journals
    ├── clients.py         # Clients, suppliers, employees
    ├── documents.py       # Sales, purchases, payments, attachments
    ├── products.py        # Products, services, warehouses, inventory
    └── reports.py         # P&L, balance sheet, quarterly
```

---

## Data formats

| Format | Value |
|--------|-------|
| Dates | `YYYY-MM-DD` |
| Decimal separator | `.` (e.g. `10.90`) |
| Currency | ISO 4217 (`EUR`, `USD`, `GBP`, ...) |
| Country | ISO 3166-1 alpha-2 (`LV`, `EE`, `LT`, `DE`, ...) |
| API I/O | UTF-8 XML (automatically parsed to JSON-like dicts) |

---

## License

Private project. All rights reserved.
