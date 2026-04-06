# PayTraq MCP

MCP (Model Context Protocol) server for integrating with [PayTraq](https://paytraq.com) — a cloud-based accounting and ERP system. Allows Claude and other MCP clients to manage PayTraq data using natural language.

---

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running](#running)
- [Claude Desktop integration](#claude-desktop-integration)
- [Available tools](#available-tools)
- [Technical limits](#technical-limits)
- [Project structure](#project-structure)
- [Data formats](#data-formats)

---

## Requirements

- Python 3.10+
- PayTraq account with API access
- `PAYTRAQ_API_TOKEN` and `PAYTRAQ_API_KEY` (found in PayTraq → Settings → API)

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

Set environment variables before starting the server:

```bash
export PAYTRAQ_API_TOKEN=your_token
export PAYTRAQ_API_KEY=your_key
```

Credentials are found in PayTraq → **Settings → API**.

---

## Running

```bash
python server.py
```

The server starts and becomes available via the MCP protocol.

---

## Claude Desktop integration

Add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "paytraq": {
      "command": "python",
      "args": ["/path/to/paytraq-mcp/server.py"],
      "env": {
        "PAYTRAQ_API_TOKEN": "your_token",
        "PAYTRAQ_API_KEY": "your_key"
      }
    }
  }
}
```

---

## Available tools

**57 tools** across 5 modules.

---

### Clients, suppliers & employees (`tools/clients.py`)

| Tool | Description |
|------|-------------|
| `list_clients` | List clients with search and pagination |
| `get_client` | Get client details by ID |
| `create_client` | Create a new client |
| `update_client` | Update client data |
| `get_client_outstanding` | Get unpaid invoices and outstanding balance for a client |
| `list_client_contacts` | List contact persons for a client |
| `add_client_contact` | Add a contact person to a client |
| `list_client_banks` | Get bank account details for a client |
| `list_client_groups` | List client groups |
| `list_suppliers` | List suppliers |
| `get_supplier` | Get supplier details |
| `create_supplier` | Create a new supplier |
| `update_supplier` | Update supplier data |
| `list_supplier_groups` | List supplier groups |
| `list_employees` | List employees |
| `get_employee` | Get employee details |
| `create_employee` | Add a new employee |
| `list_employee_groups` | List employee groups |

---

### Sales, purchases & payments (`tools/documents.py`)

| Tool | Description |
|------|-------------|
| `list_sales` | List sales documents (filters: status, date, client) |
| `get_sale` | Get invoice / order details |
| `create_sale` | Create a new sales document |
| `approve_sale` | Approve a document (draft → approved) |
| `post_sale` | Post a document to the accounting ledger |
| `void_sale` | Void a document |
| `record_sale_payment` | Record a payment received |
| `send_sale` | Email a document to a client |
| `get_sale_pdf` | Download a document as PDF |
| `list_purchases` | List purchase documents |
| `get_purchase` | Get purchase document details |
| `create_purchase` | Create a new purchase document |
| `approve_purchase` | Approve a purchase document |
| `post_purchase` | Post a purchase document to accounting |
| `record_purchase_payment` | Record a payment to a supplier |
| `list_payments` | List all payments with date filter |
| `get_payment` | Get payment details |
| `list_attachments` | List file attachments on a document |

**Supported document types (`create_sale`):**
- `sales_invoice` — standard sales invoice
- `sales_order` — sales order
- `sales_proforma` — pro-forma invoice
- `sales_receipt` — receipt
- `credit_note` — credit note

---

### Products, services & warehouse (`tools/products.py`)

| Tool | Description |
|------|-------------|
| `list_products` | List products (search by name, SKU, barcode) |
| `get_product` | Get product details |
| `create_product` | Create a new product |
| `update_product` | Update product data |
| `get_product_price_list` | Get price list for a price group |
| `set_product_price` | Set a product price |
| `list_product_groups` | List product groups |
| `list_lots` | List product lots / batches |
| `add_product_lot` | Add a new lot to a product |
| `list_services` | List service items |
| `get_service` | Get service details |
| `create_service` | Create a new service item |
| `update_service` | Update a service item |
| `list_service_groups` | List service groups |
| `list_warehouses` | List warehouses |
| `get_warehouse` | Get warehouse details |
| `get_current_inventory` | Get current stock levels at a warehouse |
| `get_product_inventory` | Get stock levels for a product across all warehouses |
| `list_loading_areas` | List loading / unloading areas |
| `list_shippers` | List shipping carriers |
| `create_shipper` | Add a new shipping carrier |

**Product types (`create_product`):**
- `1` — Storable product (tracked inventory)
- `2` — Consumable (expensed on purchase)
- `3` — Fixed asset (depreciated)

---

### Accounting (`tools/accounting.py`)

| Tool | Description |
|------|-------------|
| `list_accounts` | List chart of accounts (search by name or code) |
| `get_account` | Get account details by ID |
| `list_tax_keys` | List tax / VAT rates |
| `list_journals` | List journal entries with date filter and pagination |

---

### Financial reports (`tools/reports.py`)

| Tool | Description |
|------|-------------|
| `profit_and_loss` | Generate a P&L (income statement) for any date range |
| `balance_sheet` | Generate a balance sheet snapshot as of a given date |
| `quarterly_report` | Combined P&L + balance sheet for a full quarter |

> **Note:** Report figures are computed by aggregating general ledger journal
> entries. They may differ from official NSIS.LV / PayTraq PDF reports, which
> use the sub-ledger. No direct account-balance API endpoint is available in
> PayTraq v2.57.

---

## Technical limits

PayTraq API limits are enforced **automatically**:

| Parameter | Value |
|-----------|-------|
| Average rate | 1 request/sec |
| Burst | up to 5 requests |
| Daily limit | 5,000 requests (resets at midnight UTC) |
| Request timeout | 30 seconds |
| Page size | 100 records |

On 429 / 5xx errors the client retries automatically with exponential back-off.

---

## Project structure

```
paytraq-mcp/
├── server.py              # MCP server entry point (FastMCP)
├── paytraq_client.py      # HTTP client with rate limiting and XML parsing
├── requirements.txt       # Python dependencies
└── tools/
    ├── __init__.py
    ├── clients.py         # Clients, suppliers, employees
    ├── documents.py       # Sales, purchases, payments
    ├── products.py        # Products, services, warehouse
    ├── accounting.py      # Accounting, taxes, journals
    └── reports.py         # Financial reports (P&L, balance sheet)
```

---

## Data formats

| Format | Value |
|--------|-------|
| Dates | `YYYY-MM-DD` |
| Decimal separator | dot (e.g. `10.90`) |
| Currency code | ISO 4217 (`EUR`, `USD`, `GBP` ...) |
| Country code | ISO 3166-1 alpha-2 (`LV`, `EE`, `LT`, `DE` ...) |
| API responses | JSON (auto-converted from XML) |

---

## License

Private project. All rights reserved.
