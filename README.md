# PayTraq MCP

MCP (Model Context Protocol) serveris integrācijai ar [PayTraq](https://paytraq.com) — mākoņa grāmatvedības un ERP sistēmu. Ļauj Claude un citiem MCP klientiem pilnvērtīgi strādāt ar PayTraq datiem, izmantojot dabisko valodu.

---

## Saturs

- [Prasības](#prasības)
- [Instalācija](#instalācija)
- [Konfigurācija](#konfigurācija)
- [Palaišana](#palaišana)
- [Integrācija ar Claude Desktop](#integrācija-ar-claude-desktop)
- [Pieejamie rīki](#pieejamie-rīki)
- [Tehniskie ierobežojumi](#tehniskie-ierobežojumi)
- [Projekta struktūra](#projekta-struktūra)

---

## Prasības

- Python 3.10+
- PayTraq konts ar API piekļuvi
- `PAYTRAQ_API_TOKEN` un `PAYTRAQ_API_KEY` (iegūstami PayTraq iestatījumos)

---

## Instalācija

```bash
git clone <repozitorijs>
cd paytraq-mcp

python -m venv venv
source venv/bin/activate        # Linux / macOS
# venv\Scripts\activate.bat     # Windows

pip install -r requirements.txt
```

---

## Konfigurācija

Iestatiet vides mainīgos pirms servera palaišanas:

```bash
export PAYTRAQ_API_TOKEN=jūsu_tokens
export PAYTRAQ_API_KEY=jūsu_atslēga
```

API akreditācijas datus var atrast PayTraq → **Iestatījumi → API**.

---

## Palaišana

```bash
python server.py
```

Serveris startēs un būs pieejams caur MCP protokolu.

---

## Integrācija ar Claude Desktop

Pievienojiet konfigurāciju failā `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "paytraq": {
      "command": "python",
      "args": ["/ceļš/uz/paytraq-mcp/server.py"],
      "env": {
        "PAYTRAQ_API_TOKEN": "jūsu_tokens",
        "PAYTRAQ_API_KEY": "jūsu_atslēga"
      }
    }
  }
}
```

---

## Pieejamie rīki

Kopā: **51 rīks**, sadalīts 4 moduļos.

---

### Klienti, piegādātāji, darbinieki (`tools/clients.py`)

| Rīks | Apraksts |
|------|----------|
| `list_clients` | Klientu saraksts ar meklēšanu un lapošanu |
| `get_client` | Klienta detaļas pēc ID |
| `create_client` | Jauna klienta izveide |
| `update_client` | Klienta datu atjaunināšana |
| `get_client_outstanding` | Klienta neapmaksātie rēķini un atlikums |
| `list_client_contacts` | Klienta kontaktpersonas |
| `add_client_contact` | Kontaktpersonas pievienošana |
| `list_client_banks` | Klienta bankas rekvizīti |
| `list_client_groups` | Klientu grupas |
| `list_suppliers` | Piegādātāju saraksts |
| `get_supplier` | Piegādātāja detaļas |
| `create_supplier` | Jauna piegādātāja izveide |
| `update_supplier` | Piegādātāja datu atjaunināšana |
| `list_supplier_groups` | Piegādātāju grupas |
| `list_employees` | Darbinieku saraksts |
| `get_employee` | Darbinieka informācija |
| `create_employee` | Jauna darbinieka pievienošana |
| `list_employee_groups` | Darbinieku grupas |

---

### Dokumenti un maksājumi (`tools/documents.py`)

| Rīks | Apraksts |
|------|----------|
| `list_sales` | Pārdošanas dokumentu saraksts (filtri: statuss, datums, klients) |
| `get_sale` | Rēķina / pasūtījuma detaļas |
| `create_sale` | Jauna pārdošanas dokumenta izveide |
| `approve_sale` | Dokumenta apstiprināšana (draft → approved) |
| `post_sale` | Dokumenta iegrāmatošana grāmatvedībā |
| `void_sale` | Dokumenta anulēšana |
| `record_sale_payment` | Maksājuma reģistrēšana |
| `send_sale` | Dokumenta nosūtīšana pa e-pastu |
| `get_sale_pdf` | Dokumenta iegūšana PDF formātā |
| `list_purchases` | Iepirkumu dokumentu saraksts |
| `get_purchase` | Iepirkuma dokumenta detaļas |
| `create_purchase` | Jauna iepirkuma dokumenta izveide |
| `approve_purchase` | Iepirkuma dokumenta apstiprināšana |
| `post_purchase` | Iepirkuma iegrāmatošana |
| `record_purchase_payment` | Maksājuma reģistrēšana piegādātājam |
| `list_payments` | Maksājumu saraksts ar datumu filtru |
| `get_payment` | Maksājuma detaļas |
| `list_attachments` | Dokumenta pielikumu saraksts |

**Atbalstītie dokumentu veidi (`create_sale`):**
- `sales_invoice` — pārdošanas rēķins
- `sales_order` — pārdošanas pasūtījums
- `sales_proforma` — proforma rēķins
- `sales_receipt` — kvīts
- `credit_note` — kredītnota

---

### Preces, pakalpojumi, noliktava (`tools/products.py`)

| Rīks | Apraksts |
|------|----------|
| `list_products` | Preču saraksts (meklēšana pēc nosaukuma, SKU, svītrkoda) |
| `get_product` | Preces informācija |
| `create_product` | Jaunas preces izveide |
| `update_product` | Preces datu atjaunināšana |
| `get_product_price_list` | Cenrādis pēc cenu grupas |
| `set_product_price` | Cenas iestatīšana |
| `list_product_groups` | Preču grupas |
| `list_lots` | Partiju / lotu saraksts |
| `add_product_lot` | Jaunas partijas pievienošana |
| `list_services` | Pakalpojumu saraksts |
| `get_service` | Pakalpojuma informācija |
| `create_service` | Jauna pakalpojuma izveide |
| `update_service` | Pakalpojuma atjaunināšana |
| `list_service_groups` | Pakalpojumu grupas |
| `list_warehouses` | Noliktavu saraksts |
| `get_warehouse` | Noliktavas informācija |
| `get_current_inventory` | Pašreizējie atlikumi noliktavā |
| `get_product_inventory` | Preces atlikumi visās noliktavās |
| `list_loading_areas` | Iekraušanas / izkraušanas zonas |
| `list_shippers` | Pārvadātāju saraksts |
| `create_shipper` | Jauna pārvadātāja pievienošana |

**Preču veidi (`create_product`):**
- `1` — Noliktavas prece
- `2` — Patērējamā prece
- `3` — Pamatlīdzeklis

---

### Grāmatvedība (`tools/accounting.py`)

| Rīks | Apraksts |
|------|----------|
| `list_accounts` | Kontu plāns ar meklēšanu pēc nosaukuma vai numura |
| `get_account` | Konta informācija pēc ID |
| `list_tax_keys` | Nodokļu likmes (PVN un citi) |
| `list_journals` | Žurnāla ieraksti ar datumu filtru un lapošanu |

---

## Tehniskie ierobežojumi

PayTraq API ierobežojumi tiek ievēroti **automātiski**:

| Parametrs | Vērtība |
|-----------|---------|
| Vidējais ātrums | 1 pieprasījums/sek |
| Burst | līdz 5 pieprasījumiem |
| Dienas limits | 5 000 pieprasījumu (atiestatās pusnaktī UTC) |
| Pieprasījuma timeout | 30 sekundes |
| Lappuses izmērs | 100 ieraksti |

Kļūdu gadījumā (429, 5xx) notiek automātiska atkārtošana ar eksponenciālu aizkavi.

---

## Projekta struktūra

```
paytraq-mcp/
├── server.py              # MCP servera ieejas punkts (FastMCP)
├── paytraq_client.py      # HTTP klients ar rate limiting un XML parsēšanu
├── requirements.txt       # Python atkarības
└── tools/
    ├── __init__.py
    ├── clients.py         # Klienti, piegādātāji, darbinieki
    ├── documents.py       # Pārdošana, iepirkumi, maksājumi
    ├── products.py        # Preces, pakalpojumi, noliktava
    └── accounting.py      # Grāmatvedība, nodokļi, žurnāli
```

---

## Datu formāti

| Formāts | Vērtība |
|---------|---------|
| Datums | `YYYY-MM-DD` |
| Decimāldalītājs | punkts (piemēram, `10.90`) |
| Valūtas kods | ISO 4217 (`EUR`, `USD`, `GBP` ...) |
| Valsts kods | ISO 3166-1 alpha-2 (`LV`, `EE`, `LT`, `DE` ...) |
| API atbildes | JSON (automātiski konvertēts no XML) |

---

## Licence

Privāts projekts. Visas tiesības aizsargātas.
