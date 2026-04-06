"""
PayTraq MCP — Products, Services & Inventory Tools
----------------------------------------------------
Tools for managing:
- Products (physical goods): create, update, price, track inventory
- Services (non-physical): create and update service items
- Warehouses: list locations and check stock levels
- Lots/batches: track product batches with expiry dates
- Shippers: manage delivery carrier records

When to use these tools:
  - list_products / get_product: find product IDs before adding to an invoice
  - create_product / update_product: manage the product catalogue
  - get_current_inventory: check stock levels at a warehouse
  - get_product_inventory: see how many units of a product are across all warehouses
  - list_services / create_service: manage billable service items
"""

import re
from typing import Annotated, Optional
from pydantic import Field
from mcp.server.fastmcp import FastMCP
from paytraq_client import get, post, format_response

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

VALID_PRODUCT_TYPES = {1: "storable", 2: "consumable", 3: "fixed_asset"}
VALID_PRODUCT_STATUSES = {1: "active", 2: "discontinued"}


def _validate_date(value: Optional[str], field_name: str) -> Optional[str]:
    if value and not _DATE_RE.match(value):
        return f"Invalid {field_name} format '{value}'. Use YYYY-MM-DD (e.g. 2026-06-30)."
    return None


def register(mcp: FastMCP) -> None:

    # ── PRODUCTS ──────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_products(
        query: Annotated[Optional[str], Field(
            default=None,
            description="Search by product name, SKU/code, or barcode.",
        )] = None,
        page: Annotated[int, Field(
            default=0,
            ge=0,
            description="Page number for pagination (100 records per page).",
        )] = 0,
    ) -> str:
        """
        List products (physical goods) in the PayTraq catalogue.

        Use this tool when you need to:
        - Find a product's ItemID before adding it to an invoice or purchase order
        - Browse the full product catalogue
        - Search for a product by name, SKU, or barcode
        """
        try:
            params: dict = {"page": page}
            if query: params["query"] = query
            return format_response(get("products", params))
        except Exception as e:
            raise

    @mcp.tool()
    def get_product(
        item_id: Annotated[int, Field(
            description="Numeric PayTraq product (item) ID.",
            gt=0,
        )],
    ) -> str:
        """
        Get full details of a product by its ID.

        Use this tool to retrieve pricing, unit of measure, tax key, stock type,
        and description for a specific product.
        """
        try:
            return format_response(get(f"product/{item_id}"))
        except Exception as e:
            raise

    @mcp.tool()
    def create_product(
        name: Annotated[str, Field(description="Product name as it appears on invoices.")],
        code: Annotated[Optional[str], Field(
            default=None,
            description="SKU or internal article code.",
        )] = None,
        barcode: Annotated[Optional[str], Field(
            default=None,
            description="Product barcode (EAN, UPC, etc.).",
        )] = None,
        unit: Annotated[Optional[str], Field(
            default=None,
            description="Unit of measure (e.g. 'pcs', 'kg', 'l', 'm', 'box').",
        )] = None,
        product_type: Annotated[int, Field(
            default=1,
            description=(
                "Product type: 1 = Storable (tracked inventory), "
                "2 = Consumable (expensed on purchase), "
                "3 = Fixed Asset (depreciated)."
            ),
            ge=1,
            le=3,
        )] = 1,
        purchase_price: Annotated[Optional[float], Field(
            default=None,
            description="Default purchase/cost price. Dot as decimal separator.",
            ge=0,
        )] = None,
        sale_price: Annotated[Optional[float], Field(
            default=None,
            description="Default sale price. Dot as decimal separator.",
            ge=0,
        )] = None,
        tax_key: Annotated[Optional[str], Field(
            default=None,
            description=(
                "Tax key code for VAT calculation. "
                "Use list_tax_keys to see available keys."
            ),
        )] = None,
        description: Annotated[Optional[str], Field(
            default=None,
            description="Product description shown on documents.",
        )] = None,
        comment: Annotated[Optional[str], Field(
            default=None,
            description="Internal notes (not printed on documents).",
        )] = None,
    ) -> str:
        """
        Create a new product in the PayTraq catalogue.

        Use this tool when adding a new physical product that will appear on
        invoices or purchase orders. For non-physical billable items, use
        create_service instead.
        """
        try:
            if product_type not in VALID_PRODUCT_TYPES:
                return (
                    f"Error: Invalid product_type {product_type}. "
                    f"Valid values: 1 (storable), 2 (consumable), 3 (fixed asset)."
                )
            data: dict = {"Name": name, "Type": product_type}
            if code:            data["Code"] = code
            if barcode:         data["BarCode"] = barcode
            if unit:            data["Unit"] = unit
            if purchase_price is not None: data["PurchasePrice"] = purchase_price
            if sale_price is not None:     data["SalePrice"] = sale_price
            if tax_key:         data["TaxKey"] = tax_key
            if description:     data["Description"] = description
            if comment:         data["Comment"] = comment
            return format_response(post("product", data, "Product"))
        except Exception as e:
            raise

    @mcp.tool()
    def update_product(
        item_id: Annotated[int, Field(
            description="ID of the product to update.",
            gt=0,
        )],
        name: Annotated[Optional[str], Field(
            default=None,
            description="New product name.",
        )] = None,
        code: Annotated[Optional[str], Field(
            default=None,
            description="New SKU or article code.",
        )] = None,
        barcode: Annotated[Optional[str], Field(
            default=None,
            description="New barcode.",
        )] = None,
        unit: Annotated[Optional[str], Field(
            default=None,
            description="New unit of measure.",
        )] = None,
        purchase_price: Annotated[Optional[float], Field(
            default=None,
            description="New purchase/cost price.",
            ge=0,
        )] = None,
        sale_price: Annotated[Optional[float], Field(
            default=None,
            description="New sale price.",
            ge=0,
        )] = None,
        tax_key: Annotated[Optional[str], Field(
            default=None,
            description="New tax key. Use list_tax_keys to see options.",
        )] = None,
        description: Annotated[Optional[str], Field(
            default=None,
            description="New product description.",
        )] = None,
        status: Annotated[Optional[int], Field(
            default=None,
            description="Product status: 1 = Active, 2 = Discontinued.",
            ge=1,
            le=2,
        )] = None,
    ) -> str:
        """
        Update fields on an existing product record.

        Use this tool when a product's price, description, or status changes.
        Only the fields you provide will be updated.
        """
        try:
            if status is not None and status not in VALID_PRODUCT_STATUSES:
                return (
                    f"Error: Invalid status {status}. "
                    f"Valid values: 1 (active), 2 (discontinued)."
                )
            data: dict = {}
            if name:            data["Name"] = name
            if code:            data["Code"] = code
            if barcode:         data["BarCode"] = barcode
            if unit:            data["Unit"] = unit
            if purchase_price is not None: data["PurchasePrice"] = purchase_price
            if sale_price is not None:     data["SalePrice"] = sale_price
            if tax_key:         data["TaxKey"] = tax_key
            if description:     data["Description"] = description
            if status is not None: data["Status"] = status
            if not data:
                return "Error: Provide at least one field to update."
            return format_response(post(f"product/{item_id}", data, "Product"))
        except Exception as e:
            raise

    @mcp.tool()
    def get_product_price_list(
        price_group_id: Annotated[int, Field(
            description="Price group ID. Use list_client_groups or ask the user for it.",
            gt=0,
        )],
    ) -> str:
        """
        Get the product price list for a specific price group.

        Use this tool when a customer has a special pricing agreement and you need
        to see what prices apply to them (e.g. wholesale vs retail).
        """
        try:
            return format_response(get(f"productPriceList/{price_group_id}"))
        except Exception as e:
            raise

    @mcp.tool()
    def set_product_price(
        item_id: Annotated[int, Field(
            description="Product ID to set a price for.",
            gt=0,
        )],
        price: Annotated[float, Field(
            description="New price. Dot as decimal separator (e.g. 29.99).",
            ge=0,
        )],
        price_group_id: Annotated[Optional[int], Field(
            default=None,
            description="Price group ID. If omitted, updates the standard/default price.",
            gt=0,
        )] = None,
        currency: Annotated[Optional[str], Field(
            default=None,
            description="ISO 4217 currency code for this price (e.g. EUR, USD).",
        )] = None,
    ) -> str:
        """
        Set or update the price of a product, optionally for a specific price group.

        Use this tool when changing a product's sale price, or setting a
        special price for a customer group (e.g. wholesale, VIP).
        """
        try:
            data: dict = {"Price": price}
            if price_group_id: data["PriceGroupID"] = price_group_id
            if currency:       data["Currency"] = currency.upper()
            return format_response(post(f"productPrice/{item_id}", data, "Price"))
        except Exception as e:
            raise

    @mcp.tool()
    def list_product_groups() -> str:
        """
        List all product groups (categories) in PayTraq.

        Use this tool to get group IDs when organizing products or filtering
        the product catalogue by category.
        """
        try:
            return format_response(get("productGroups"))
        except Exception as e:
            raise

    @mcp.tool()
    def list_lots(
        item_id: Annotated[Optional[int], Field(
            default=None,
            description="Filter lots by product ID. Leave empty to list all lots.",
            gt=0,
        )] = None,
        page: Annotated[int, Field(
            default=0,
            ge=0,
            description="Page number (100 records per page).",
        )] = 0,
    ) -> str:
        """
        List product lots/batches, optionally filtered by product.

        Use this tool when tracking batch numbers or expiry dates for
        perishable goods, pharmaceuticals, or serialised inventory.
        """
        try:
            params: dict = {"page": page}
            if item_id: params["item_id"] = item_id
            return format_response(get("lots", params))
        except Exception as e:
            raise

    @mcp.tool()
    def add_product_lot(
        item_id: Annotated[int, Field(
            description="Product ID to assign this lot to.",
            gt=0,
        )],
        lot_number: Annotated[str, Field(
            description="Batch or lot number (e.g. 'LOT-2026-001').",
        )],
        expiry_date: Annotated[Optional[str], Field(
            default=None,
            description="Expiry/best-before date in YYYY-MM-DD format.",
        )] = None,
        quantity: Annotated[Optional[float], Field(
            default=None,
            description="Initial quantity in this lot.",
            ge=0,
        )] = None,
        comment: Annotated[Optional[str], Field(
            default=None,
            description="Notes about this lot (e.g. supplier batch info).",
        )] = None,
    ) -> str:
        """
        Add a new lot/batch to a product for batch tracking.

        Use this tool when receiving goods that require lot or batch number
        tracking (e.g. food products, chemicals, medical supplies).
        """
        try:
            err = _validate_date(expiry_date, "expiry_date")
            if err:
                return f"Error: {err}"
            data: dict = {"LotNumber": lot_number}
            if expiry_date: data["ExpiryDate"] = expiry_date
            if quantity is not None: data["Qty"] = quantity
            if comment:     data["Comment"] = comment
            return format_response(post(f"product/lot/{item_id}", data, "Lot"))
        except Exception as e:
            raise

    # ── SERVICES ──────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_services(
        query: Annotated[Optional[str], Field(
            default=None,
            description="Search by service name or code.",
        )] = None,
        page: Annotated[int, Field(
            default=0,
            ge=0,
            description="Page number (100 records per page).",
        )] = 0,
    ) -> str:
        """
        List service items in the PayTraq catalogue.

        Use this tool when you need to find a service ID before adding it to
        an invoice. Services are non-physical billable items (consulting, shipping, etc.).
        """
        try:
            params: dict = {"page": page}
            if query: params["query"] = query
            return format_response(get("services", params))
        except Exception as e:
            raise

    @mcp.tool()
    def get_service(
        item_id: Annotated[int, Field(
            description="Numeric PayTraq service item ID.",
            gt=0,
        )],
    ) -> str:
        """
        Get full details of a service item by ID.

        Use this tool to retrieve pricing, tax key, and description for
        a specific service.
        """
        try:
            return format_response(get(f"service/{item_id}"))
        except Exception as e:
            raise

    @mcp.tool()
    def create_service(
        name: Annotated[str, Field(description="Service name as it appears on invoices.")],
        code: Annotated[Optional[str], Field(
            default=None,
            description="Internal service code or SKU.",
        )] = None,
        unit: Annotated[Optional[str], Field(
            default=None,
            description="Billing unit (e.g. 'hour', 'day', 'project', 'month').",
        )] = None,
        sale_price: Annotated[Optional[float], Field(
            default=None,
            description="Default price per unit. Dot as decimal separator.",
            ge=0,
        )] = None,
        tax_key: Annotated[Optional[str], Field(
            default=None,
            description="Tax key for VAT. Use list_tax_keys to see available keys.",
        )] = None,
        description: Annotated[Optional[str], Field(
            default=None,
            description="Service description printed on invoice line items.",
        )] = None,
    ) -> str:
        """
        Create a new service item in the PayTraq catalogue.

        Use this tool when adding a new billable service (consulting, support,
        delivery, etc.) that will appear on sales invoices.
        """
        try:
            data: dict = {"Name": name}
            if code:        data["Code"] = code
            if unit:        data["Unit"] = unit
            if sale_price is not None: data["SalePrice"] = sale_price
            if tax_key:     data["TaxKey"] = tax_key
            if description: data["Description"] = description
            return format_response(post("service", data, "Service"))
        except Exception as e:
            raise

    @mcp.tool()
    def update_service(
        item_id: Annotated[int, Field(
            description="ID of the service to update.",
            gt=0,
        )],
        name: Annotated[Optional[str], Field(
            default=None,
            description="New service name.",
        )] = None,
        code: Annotated[Optional[str], Field(
            default=None,
            description="New service code.",
        )] = None,
        sale_price: Annotated[Optional[float], Field(
            default=None,
            description="New sale price.",
            ge=0,
        )] = None,
        tax_key: Annotated[Optional[str], Field(
            default=None,
            description="New tax key.",
        )] = None,
        description: Annotated[Optional[str], Field(
            default=None,
            description="New service description.",
        )] = None,
    ) -> str:
        """
        Update fields on an existing service item.

        Use this tool when a service price or description changes.
        Only provided fields are updated.
        """
        try:
            data: dict = {}
            if name:        data["Name"] = name
            if code:        data["Code"] = code
            if sale_price is not None: data["SalePrice"] = sale_price
            if tax_key:     data["TaxKey"] = tax_key
            if description: data["Description"] = description
            if not data:
                return "Error: Provide at least one field to update."
            return format_response(post(f"service/{item_id}", data, "Service"))
        except Exception as e:
            raise

    @mcp.tool()
    def list_service_groups() -> str:
        """
        List all service groups (categories) in PayTraq.

        Use this tool to get group IDs for filtering services or assigning
        a new service to an existing category.
        """
        try:
            return format_response(get("serviceGroups"))
        except Exception as e:
            raise

    # ── WAREHOUSES & INVENTORY ────────────────────────────────────────────────

    @mcp.tool()
    def list_warehouses() -> str:
        """
        List all warehouses configured in PayTraq.

        Use this tool to find warehouse IDs before checking inventory levels
        or creating stock movements.
        """
        try:
            return format_response(get("warehouses"))
        except Exception as e:
            raise

    @mcp.tool()
    def get_warehouse(
        warehouse_id: Annotated[int, Field(
            description="Numeric PayTraq warehouse ID.",
            gt=0,
        )],
    ) -> str:
        """
        Get details of a specific warehouse (name, address, loading areas).

        Use this tool when you need the full configuration of a warehouse location.
        """
        try:
            return format_response(get(f"warehouse/{warehouse_id}"))
        except Exception as e:
            raise

    @mcp.tool()
    def get_current_inventory(
        warehouse_id: Annotated[int, Field(
            description="Warehouse ID to check current stock levels at.",
            gt=0,
        )],
    ) -> str:
        """
        Get current stock levels for all products at a specific warehouse.

        Use this tool when you need to know:
        - What is in stock at a given location
        - Whether there is enough inventory to fulfil an order
        - Overall warehouse stock report
        """
        try:
            return format_response(get(f"currentInventory/{warehouse_id}"))
        except Exception as e:
            raise

    @mcp.tool()
    def get_product_inventory(
        item_id: Annotated[int, Field(
            description="Product ID to check inventory across all warehouses.",
            gt=0,
        )],
    ) -> str:
        """
        Get stock levels for a specific product across all warehouses.

        Use this tool when you need to know the total available quantity of a
        product and where it is physically located.
        """
        try:
            return format_response(get(f"productInventory/{item_id}"))
        except Exception as e:
            raise

    @mcp.tool()
    def list_loading_areas() -> str:
        """
        List all loading/unloading areas defined in PayTraq.

        Use this tool when configuring shipment routing or dispatch zones
        in warehouse operations.
        """
        try:
            return format_response(get("loadingAreas"))
        except Exception as e:
            raise

    @mcp.tool()
    def list_shippers(
        page: Annotated[int, Field(
            default=0,
            ge=0,
            description="Page number (100 records per page).",
        )] = 0,
    ) -> str:
        """
        List all shipping carriers/shippers configured in PayTraq.

        Use this tool to find shipper IDs when assigning a carrier to a
        sales or delivery document.
        """
        try:
            return format_response(get("shippers", {"page": page}))
        except Exception as e:
            raise

    @mcp.tool()
    def create_shipper(
        name: Annotated[str, Field(description="Carrier/shipping company name.")],
        contact: Annotated[Optional[str], Field(
            default=None,
            description="Contact person at the carrier.",
        )] = None,
        phone: Annotated[Optional[str], Field(
            default=None,
            description="Carrier's phone number.",
        )] = None,
        email: Annotated[Optional[str], Field(
            default=None,
            description="Carrier's email address.",
        )] = None,
    ) -> str:
        """
        Add a new shipping carrier (shipper) to PayTraq.

        Use this tool when you start working with a new delivery company and
        need to register them for use on shipping documents.
        """
        try:
            import re as _re
            if email and not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                return f"Error: Invalid email address '{email}'."
            data: dict = {"ShipperName": name}
            if contact: data["Contact"] = contact
            if phone:   data["Phone"] = phone
            if email:   data["Email"] = email
            return format_response(post("shipper", data, "Shipper"))
        except Exception as e:
            raise
