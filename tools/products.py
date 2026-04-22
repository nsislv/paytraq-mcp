"""
PayTraq MCP — Products, Services, Warehouses, Inventory, and Shippers.

Products   = physical goods (tracked inventory, consumables, fixed assets)
Services   = non-physical billable items (consulting, shipping, subscriptions)
Warehouses = physical stock locations
Lots       = batches with expiry tracking (food, pharma, chemicals)
Shippers   = delivery carrier records
"""

from __future__ import annotations

from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from paytraq_client import (
    PaytraqBadRequest,
    format_list,
    format_single,
    get,
    parse_list,
    post,
)
from tools._common import (
    ResponseFormat,
    drop_none,
    ensure_currency,
    ensure_date,
    ensure_email,
)

PRODUCT_TYPES: dict[int, str] = {
    1: "storable (tracked inventory)",
    2: "consumable (expensed on purchase)",
    3: "fixed_asset (depreciated)",
}
PRODUCT_STATUSES: dict[int, str] = {1: "active", 2: "discontinued"}


READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
WRITE_ADDITIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
)
WRITE_UPDATE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True
)


def register(mcp: FastMCP) -> None:

    # ── Products ──────────────────────────────────────────────────────────────

    @mcp.tool(
        name="paytraq_list_products",
        title="List products",
        annotations=READ_ONLY,
    )
    def paytraq_list_products(
        query: Annotated[Optional[str], Field(
            description="Search by name, SKU/code, or barcode.",
        )] = None,
        page: Annotated[int, Field(ge=0, description="0-indexed page (100/page).")] = 0,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """List products (physical goods). Use to find ItemIDs before adding to documents."""
        params: dict = {"page": page}
        if query:
            params["query"] = query
        parsed = get("products", params)
        return format_list(parse_list(parsed, page=page), response_format.value)

    @mcp.tool(
        name="paytraq_get_product",
        title="Get product details",
        annotations=READ_ONLY,
    )
    def paytraq_get_product(
        item_id: Annotated[int, Field(gt=0, description="Numeric ItemID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Return full product record: prices, unit, tax key, stock type, description."""
        parsed = get(f"product/{item_id}")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_create_product",
        title="Create a product",
        annotations=WRITE_ADDITIVE,
    )
    def paytraq_create_product(
        name: Annotated[str, Field(min_length=1, description="Product name shown on invoices.")],
        code: Annotated[Optional[str], Field(description="SKU / internal article code.")] = None,
        barcode: Annotated[Optional[str], Field(description="EAN / UPC barcode.")] = None,
        unit: Annotated[Optional[str], Field(
            description="Unit of measure: pcs, kg, l, m, box, etc.",
        )] = None,
        product_type: Annotated[int, Field(
            ge=1, le=3,
            description="1=storable (tracked), 2=consumable (expensed), 3=fixed_asset (depreciated).",
        )] = 1,
        purchase_price: Annotated[Optional[float], Field(
            ge=0, description="Default cost price.",
        )] = None,
        sale_price: Annotated[Optional[float], Field(
            ge=0, description="Default sale price.",
        )] = None,
        tax_key: Annotated[Optional[str], Field(
            description="TaxKey code for VAT (from paytraq_list_tax_keys).",
        )] = None,
        description: Annotated[Optional[str], Field(
            description="Long-form description shown on documents.",
        )] = None,
        comment: Annotated[Optional[str], Field(
            description="Internal-only notes (not printed).",
        )] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        Create a new product in the catalogue.

        For non-physical billable items (hours, subscriptions), use
        paytraq_create_service instead.
        """
        if product_type not in PRODUCT_TYPES:
            raise PaytraqBadRequest(
                f"Invalid product_type={product_type}. Allowed: "
                + ", ".join(f"{k} ({v})" for k, v in PRODUCT_TYPES.items())
            )

        data = drop_none({
            "Name": name,
            "Type": product_type,
            "Code": code,
            "BarCode": barcode,
            "Unit": unit,
            "PurchasePrice": purchase_price,
            "SalePrice": sale_price,
            "TaxKey": tax_key,
            "Description": description,
            "Comment": comment,
        })
        parsed = post("product", data, "Product")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_update_product",
        title="Update a product",
        annotations=WRITE_UPDATE,
    )
    def paytraq_update_product(
        item_id: Annotated[int, Field(gt=0, description="ItemID to update.")],
        name: Annotated[Optional[str], Field(description="New name.")] = None,
        code: Annotated[Optional[str], Field(description="New SKU.")] = None,
        barcode: Annotated[Optional[str], Field(description="New barcode.")] = None,
        unit: Annotated[Optional[str], Field(description="New unit of measure.")] = None,
        purchase_price: Annotated[Optional[float], Field(
            ge=0, description="New cost price.",
        )] = None,
        sale_price: Annotated[Optional[float], Field(
            ge=0, description="New sale price.",
        )] = None,
        tax_key: Annotated[Optional[str], Field(description="New TaxKey code.")] = None,
        description: Annotated[Optional[str], Field(description="New description.")] = None,
        status: Annotated[Optional[int], Field(
            ge=1, le=2,
            description="Status: 1=active, 2=discontinued.",
        )] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Update fields on an existing product. Omitted fields unchanged."""
        if status is not None and status not in PRODUCT_STATUSES:
            raise PaytraqBadRequest(
                f"Invalid status={status}. Allowed: "
                + ", ".join(f"{k} ({v})" for k, v in PRODUCT_STATUSES.items())
            )

        data = drop_none({
            "Name": name,
            "Code": code,
            "BarCode": barcode,
            "Unit": unit,
            "PurchasePrice": purchase_price,
            "SalePrice": sale_price,
            "TaxKey": tax_key,
            "Description": description,
            "Status": status,
        })
        if not data:
            raise PaytraqBadRequest(
                "No fields supplied — pass at least one of name/code/price/... to update."
            )
        parsed = post(f"product/{item_id}", data, "Product")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_get_product_price_list",
        title="Get product prices for a price group",
        annotations=READ_ONLY,
    )
    def paytraq_get_product_price_list(
        price_group_id: Annotated[int, Field(gt=0, description="PriceGroupID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        Return prices applicable to a specific price group (e.g. wholesale, retail, VIP).
        Useful when a customer has a special pricing agreement.
        """
        parsed = get(f"productPriceList/{price_group_id}")
        result = parse_list(parsed, page=0)
        return format_list(result, response_format.value)

    @mcp.tool(
        name="paytraq_set_product_price",
        title="Set a product price",
        annotations=WRITE_UPDATE,
    )
    def paytraq_set_product_price(
        item_id: Annotated[int, Field(gt=0, description="Product ItemID.")],
        price: Annotated[float, Field(
            ge=0, description="New price (e.g. 29.99).",
        )],
        price_group_id: Annotated[Optional[int], Field(
            gt=0, description="PriceGroupID. Omit to update the default price.",
        )] = None,
        currency: Annotated[Optional[str], Field(
            description="ISO 4217 currency (EUR, USD, ...).",
        )] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        Set the price of a product. If price_group_id is omitted, the default
        price is updated; otherwise a group-specific price is set.
        """
        data = drop_none({
            "Price": price,
            "PriceGroupID": price_group_id,
            "Currency": ensure_currency(currency),
        })
        parsed = post(f"productPrice/{item_id}", data, "Price")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_list_product_groups",
        title="List product groups",
        annotations=READ_ONLY,
    )
    def paytraq_list_product_groups(
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """List product groups (categories)."""
        parsed = get("productGroups")
        result = parse_list(parsed, page=0)
        return format_list(result, response_format.value)

    @mcp.tool(
        name="paytraq_list_lots",
        title="List product lots / batches",
        annotations=READ_ONLY,
    )
    def paytraq_list_lots(
        item_id: Annotated[Optional[int], Field(
            gt=0, description="Filter to one product. Omit for all lots.",
        )] = None,
        page: Annotated[int, Field(ge=0, description="0-indexed page (100/page).")] = 0,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """List lots/batches (with expiry dates) for perishables or pharma."""
        params: dict = {"page": page}
        if item_id:
            params["item_id"] = item_id
        parsed = get("lots", params)
        return format_list(parse_list(parsed, page=page), response_format.value)

    @mcp.tool(
        name="paytraq_add_product_lot",
        title="Add a product lot",
        annotations=WRITE_ADDITIVE,
    )
    def paytraq_add_product_lot(
        item_id: Annotated[int, Field(gt=0, description="ItemID this lot belongs to.")],
        lot_number: Annotated[str, Field(
            min_length=1, description="Batch / lot number (e.g. 'LOT-2026-001').",
        )],
        expiry_date: Annotated[Optional[str], Field(
            description="Best-before date (YYYY-MM-DD).",
        )] = None,
        quantity: Annotated[Optional[float], Field(
            ge=0, description="Initial quantity in this lot.",
        )] = None,
        comment: Annotated[Optional[str], Field(
            description="Lot notes (supplier batch code, etc.).",
        )] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Attach a new lot/batch to a product for batch tracking."""
        ensure_date(expiry_date, "expiry_date")
        data = drop_none({
            "LotNumber": lot_number,
            "ExpiryDate": expiry_date,
            "Qty": quantity,
            "Comment": comment,
        })
        parsed = post(f"product/lot/{item_id}", data, "Lot")
        return format_single(parsed, response_format.value)

    # ── Services ──────────────────────────────────────────────────────────────

    @mcp.tool(
        name="paytraq_list_services",
        title="List services",
        annotations=READ_ONLY,
    )
    def paytraq_list_services(
        query: Annotated[Optional[str], Field(
            description="Search by service name or code.",
        )] = None,
        page: Annotated[int, Field(ge=0, description="0-indexed page (100/page).")] = 0,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """List service items (non-physical billables — consulting, support, shipping...)."""
        params: dict = {"page": page}
        if query:
            params["query"] = query
        parsed = get("services", params)
        return format_list(parse_list(parsed, page=page), response_format.value)

    @mcp.tool(
        name="paytraq_get_service",
        title="Get service details",
        annotations=READ_ONLY,
    )
    def paytraq_get_service(
        item_id: Annotated[int, Field(gt=0, description="Service ItemID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Return full service record: pricing, tax key, description."""
        parsed = get(f"service/{item_id}")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_create_service",
        title="Create a service",
        annotations=WRITE_ADDITIVE,
    )
    def paytraq_create_service(
        name: Annotated[str, Field(min_length=1, description="Service name on invoices.")],
        code: Annotated[Optional[str], Field(description="Service code / SKU.")] = None,
        unit: Annotated[Optional[str], Field(
            description="Billing unit: hour, day, project, month, etc.",
        )] = None,
        sale_price: Annotated[Optional[float], Field(
            ge=0, description="Default price per unit.",
        )] = None,
        tax_key: Annotated[Optional[str], Field(
            description="TaxKey code (from paytraq_list_tax_keys).",
        )] = None,
        description: Annotated[Optional[str], Field(
            description="Description printed on invoice line items.",
        )] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Create a new service item for the catalogue."""
        data = drop_none({
            "Name": name,
            "Code": code,
            "Unit": unit,
            "SalePrice": sale_price,
            "TaxKey": tax_key,
            "Description": description,
        })
        parsed = post("service", data, "Service")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_update_service",
        title="Update a service",
        annotations=WRITE_UPDATE,
    )
    def paytraq_update_service(
        item_id: Annotated[int, Field(gt=0, description="Service ItemID.")],
        name: Annotated[Optional[str], Field(description="New name.")] = None,
        code: Annotated[Optional[str], Field(description="New service code.")] = None,
        sale_price: Annotated[Optional[float], Field(
            ge=0, description="New sale price.",
        )] = None,
        tax_key: Annotated[Optional[str], Field(description="New TaxKey.")] = None,
        description: Annotated[Optional[str], Field(description="New description.")] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Update fields on an existing service. Omitted fields unchanged."""
        data = drop_none({
            "Name": name,
            "Code": code,
            "SalePrice": sale_price,
            "TaxKey": tax_key,
            "Description": description,
        })
        if not data:
            raise PaytraqBadRequest(
                "No fields supplied — pass at least one of name/code/price/... to update."
            )
        parsed = post(f"service/{item_id}", data, "Service")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_list_service_groups",
        title="List service groups",
        annotations=READ_ONLY,
    )
    def paytraq_list_service_groups(
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """List service groups (categories)."""
        parsed = get("serviceGroups")
        result = parse_list(parsed, page=0)
        return format_list(result, response_format.value)

    # ── Warehouses & inventory ────────────────────────────────────────────────

    @mcp.tool(
        name="paytraq_list_warehouses",
        title="List warehouses",
        annotations=READ_ONLY,
    )
    def paytraq_list_warehouses(
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """List warehouses. Use to find WarehouseIDs for inventory queries."""
        parsed = get("warehouses")
        result = parse_list(parsed, page=0)
        return format_list(result, response_format.value)

    @mcp.tool(
        name="paytraq_get_warehouse",
        title="Get warehouse details",
        annotations=READ_ONLY,
    )
    def paytraq_get_warehouse(
        warehouse_id: Annotated[int, Field(gt=0, description="Numeric WarehouseID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Return full warehouse record: name, address, loading areas."""
        parsed = get(f"warehouse/{warehouse_id}")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_get_current_inventory",
        title="Get current stock at a warehouse",
        annotations=READ_ONLY,
    )
    def paytraq_get_current_inventory(
        warehouse_id: Annotated[int, Field(gt=0, description="WarehouseID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        Return current stock levels for every product at one warehouse.

        Use when you need a full on-hand report for a location or to decide
        whether stock is sufficient to fulfil an order.
        """
        parsed = get(f"currentInventory/{warehouse_id}")
        result = parse_list(parsed, page=0)
        return format_list(result, response_format.value)

    @mcp.tool(
        name="paytraq_get_product_inventory",
        title="Get one product's stock across warehouses",
        annotations=READ_ONLY,
    )
    def paytraq_get_product_inventory(
        item_id: Annotated[int, Field(gt=0, description="Product ItemID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Return stock levels for one product at every warehouse where it exists."""
        parsed = get(f"productInventory/{item_id}")
        result = parse_list(parsed, page=0)
        return format_list(result, response_format.value)

    @mcp.tool(
        name="paytraq_list_loading_areas",
        title="List loading areas",
        annotations=READ_ONLY,
    )
    def paytraq_list_loading_areas(
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """List loading/unloading dock areas configured in PayTraq."""
        parsed = get("loadingAreas")
        result = parse_list(parsed, page=0)
        return format_list(result, response_format.value)

    @mcp.tool(
        name="paytraq_list_shippers",
        title="List shipping carriers",
        annotations=READ_ONLY,
    )
    def paytraq_list_shippers(
        page: Annotated[int, Field(ge=0, description="0-indexed page (100/page).")] = 0,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """List shipping carriers. Use to find a ShipperID for delivery documents."""
        parsed = get("shippers", {"page": page})
        return format_list(parse_list(parsed, page=page), response_format.value)

    @mcp.tool(
        name="paytraq_create_shipper",
        title="Create a shipping carrier",
        annotations=WRITE_ADDITIVE,
    )
    def paytraq_create_shipper(
        name: Annotated[str, Field(min_length=1, description="Carrier company name.")],
        contact: Annotated[Optional[str], Field(description="Contact person.")] = None,
        phone: Annotated[Optional[str], Field(description="Carrier phone.")] = None,
        email: Annotated[Optional[str], Field(description="Carrier email.")] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Register a new shipping carrier for use on delivery documents."""
        email = ensure_email(email)
        data = drop_none({
            "ShipperName": name,
            "Contact": contact,
            "Phone": phone,
            "Email": email,
        })
        parsed = post("shipper", data, "Shipper")
        return format_single(parsed, response_format.value)
