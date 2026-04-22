"""
PayTraq MCP — Sales, purchases, payments, and attachments.

Covers the document lifecycle:
  draft → approved → posted → paid (or voided)

Line items for create_sale / create_purchase must be a list of dicts, each with
ItemID / Qty / Price at a minimum. The XML builder serialises lists as repeated
elements so `{"LineItems": [{...}, {...}]}` becomes valid PayTraq XML.
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

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
    ensure_in,
)

VALID_STATUSES: set[str] = {
    "draft", "approved", "posted", "paid", "wait_payment", "voided",
}
VALID_SALE_TYPES: set[str] = {
    "sales_invoice", "sales_order", "sales_proforma", "sales_receipt", "credit_note",
}
VALID_OPERATIONS: set[str] = {"sell_goods", "sell_services", "other_income"}


def _amount_due(item: Any) -> float:
    """
    Extract AmountDue from a list item's Header block as a float. Returns 0.0
    when the field is missing, empty, or unparseable — an unreadable balance
    is treated as zero so _is_unpaid() stays conservative.
    """
    if not isinstance(item, dict):
        return 0.0
    header = item.get("Header") if isinstance(item.get("Header"), dict) else item
    raw = header.get("AmountDue", "0") if isinstance(header, dict) else "0"
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def _is_unpaid(item: Any) -> bool:
    """True if the document has an outstanding balance (AmountDue > 0)."""
    return _amount_due(item) > 0


READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
WRITE_ADDITIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
)
WRITE_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
WRITE_DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True
)
WRITE_SEND = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
)


def _normalise_line_items(items: Optional[list]) -> Optional[list[dict]]:
    """
    Validate and normalise line-item dicts for create_sale / create_purchase.
    Each item must be a mapping; ItemID is required, Qty/Price recommended.
    """
    if items is None:
        return None
    if not isinstance(items, list) or not items:
        raise PaytraqBadRequest(
            "Line items must be a non-empty list of dicts, e.g. "
            '[{"ItemID": 42, "Qty": 2, "Price": 15.00}].'
        )
    normalised: list[dict] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise PaytraqBadRequest(
                f"Line item #{idx + 1} must be a dict with keys ItemID / Qty / Price."
            )
        if "ItemID" not in item:
            raise PaytraqBadRequest(
                f"Line item #{idx + 1} is missing 'ItemID' — call "
                "paytraq_list_products or paytraq_list_services to find it."
            )
        normalised.append({k: v for k, v in item.items() if v is not None})
    return normalised


def register(mcp: FastMCP) -> None:

    # ── Sales documents ───────────────────────────────────────────────────────

    @mcp.tool(
        name="paytraq_list_sales",
        title="List sales documents",
        annotations=READ_ONLY,
    )
    def paytraq_list_sales(
        status: Annotated[Optional[str], Field(
            description=(
                "Filter by status. One of: "
                f"{', '.join(sorted(VALID_STATUSES))}. "
                "Note: PayTraq's status filter is imprecise for outstanding "
                "balances — prefer `unpaid_only=True` to find invoices that "
                "still owe money regardless of status."
            ),
        )] = None,
        date_from: Annotated[Optional[str], Field(
            description="Document date lower bound (YYYY-MM-DD).",
        )] = None,
        date_till: Annotated[Optional[str], Field(
            description="Document date upper bound (YYYY-MM-DD).",
        )] = None,
        client_id: Annotated[Optional[int], Field(
            gt=0, description="Filter to one ClientID.",
        )] = None,
        query: Annotated[Optional[str], Field(
            description="Text search by document number or reference.",
        )] = None,
        unpaid_only: Annotated[bool, Field(
            description=(
                "If True, keep only documents with AmountDue > 0 (reliable "
                "'unpaid' filter that works regardless of DocumentStatus). "
                "Applied client-side after the PayTraq query, so combine with "
                "date_from/date_till to avoid paging through many paid docs."
            ),
        )] = False,
        page: Annotated[int, Field(ge=0, description="0-indexed page (100/page).")] = 0,
        reverse: Annotated[bool, Field(
            description=(
                "False (default) = newest-first ordering. True = reverse to "
                "oldest-first. NB: PayTraq's natural order is descending by "
                "DocumentDate, so `reverse=True` flips it to ascending."
            ),
        )] = False,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        List sales documents (invoices, orders, receipts, proformas, credit notes).

        Common filters:
          - unpaid_only=True → only documents with outstanding balance
          - client_id=N → all documents for one customer
          - date_from / date_till → period-based reporting

        Tip: the response is capped at ~25 000 chars. If you see a
        "response shrunk from N to M items" note, narrow the date range or
        add a filter — do NOT assume the unseen items are absent, they were
        simply trimmed from the page payload.
        """
        ensure_in(status, VALID_STATUSES, "status")
        ensure_date(date_from, "date_from")
        ensure_date(date_till, "date_till")

        params: dict = {"page": page}
        if status:    params["status"] = status
        if date_from: params["date_from"] = date_from
        if date_till: params["date_till"] = date_till
        if client_id: params["client_id"] = client_id
        if query:     params["query"] = query
        if reverse:   params["reverse"] = "true"
        parsed = get("sales", params)
        result = parse_list(parsed, page=page)
        if unpaid_only:
            result.items = [it for it in result.items if _is_unpaid(it)]
            result.count = len(result.items)
        return format_list(result, response_format.value)

    @mcp.tool(
        name="paytraq_get_sale",
        title="Get a sales document",
        annotations=READ_ONLY,
    )
    def paytraq_get_sale(
        document_id: Annotated[int, Field(gt=0, description="Sales DocumentID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Return full sales document: line items, totals, due date, payment status, client."""
        parsed = get(f"sale/{document_id}")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_create_sale",
        title="Create a sales document",
        annotations=WRITE_ADDITIVE,
    )
    def paytraq_create_sale(
        client_id: Annotated[int, Field(gt=0, description="Target ClientID (customer).")],
        document_date: Annotated[str, Field(
            description="Document date (YYYY-MM-DD).",
        )],
        sale_type: Annotated[str, Field(
            description=(
                "Document type. One of: sales_invoice, sales_order, sales_proforma, "
                "sales_receipt, credit_note."
            ),
        )] = "sales_invoice",
        operation: Annotated[str, Field(
            description="Revenue type: sell_goods | sell_services | other_income.",
        )] = "sell_goods",
        currency: Annotated[str, Field(
            description="ISO 4217 currency (EUR, USD, ...).",
        )] = "EUR",
        items: Annotated[Optional[list], Field(
            description=(
                "Line items — a list of dicts with keys ItemID (int, required), "
                "Qty (number), Price (number). "
                'Example: [{"ItemID": 42, "Qty": 2, "Price": 150.00}, '
                '{"ItemID": 99, "Qty": 1, "Price": 49.50}]'
            ),
        )] = None,
        ref_number: Annotated[Optional[str], Field(
            description="External reference (e.g. the customer's PO number).",
        )] = None,
        due_date: Annotated[Optional[str], Field(
            description="Payment due date (YYYY-MM-DD).",
        )] = None,
        comment: Annotated[Optional[str], Field(
            description="Notes printed on the document.",
        )] = None,
        warehouse_id: Annotated[Optional[int], Field(
            gt=0, description="Source WarehouseID for goods.",
        )] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        Create a new sales document and return its DocumentID.

        The document starts in 'draft' status. The workflow is:
          1. paytraq_create_sale         → draft
          2. paytraq_approve_sale        → approved
          3. paytraq_post_sale           → posted (creates journal entries)
          4. paytraq_record_sale_payment → paid
        """
        ensure_date(document_date, "document_date")
        ensure_date(due_date, "due_date")
        ensure_in(sale_type, VALID_SALE_TYPES, "sale_type")
        ensure_in(operation, VALID_OPERATIONS, "operation")
        currency = ensure_currency(currency) or "EUR"
        line_items = _normalise_line_items(items)

        data: dict[str, Any] = drop_none({
            "ClientID": client_id,
            "DocumentDate": document_date,
            "SaleType": sale_type,
            "Operation": operation,
            "Currency": currency,
            "DocumentRef": ref_number,
            "DueDate": due_date,
            "Comment": comment,
            "WarehouseID": warehouse_id,
        })
        if line_items:
            # build_xml expands lists as repeated <LineItem> siblings.
            data["LineItems"] = {"LineItem": line_items}

        parsed = post("sales", data, "Document")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_approve_sale",
        title="Approve a sales document",
        annotations=WRITE_IDEMPOTENT,
    )
    def paytraq_approve_sale(
        document_id: Annotated[int, Field(gt=0, description="DocumentID to approve.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        Move a sales document from 'draft' to 'approved'.

        Approved documents can be emailed to the customer and then posted to
        the accounting ledger.
        """
        parsed = post(f"sale/{document_id}/approve", {}, "Document")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_post_sale",
        title="Post a sales document to the ledger",
        annotations=WRITE_IDEMPOTENT,
    )
    def paytraq_post_sale(
        document_id: Annotated[int, Field(gt=0, description="DocumentID to post.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        Post an approved sales document to the general ledger.

        This creates immutable journal entries and changes status from 'approved'
        to 'posted'. Reversing a posted document requires a credit_note.
        """
        parsed = post(f"sale/{document_id}/post", {}, "Document")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_void_sale",
        title="Void a sales document",
        annotations=WRITE_DESTRUCTIVE,
    )
    def paytraq_void_sale(
        document_id: Annotated[int, Field(gt=0, description="DocumentID to void.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        Void (cancel) a sales document — cannot be undone.

        Use only for drafts created in error. For posted/paid documents, issue a
        credit_note via paytraq_create_sale instead to preserve the audit trail.
        """
        parsed = post(f"sale/{document_id}/void", {}, "Document")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_record_sale_payment",
        title="Record a customer payment",
        annotations=WRITE_ADDITIVE,
    )
    def paytraq_record_sale_payment(
        document_id: Annotated[int, Field(gt=0, description="Sales DocumentID being paid.")],
        amount: Annotated[float, Field(
            gt=0,
            description="Payment amount with dot decimal separator (e.g. 150.00).",
        )],
        payment_date: Annotated[str, Field(
            description="Date payment was received (YYYY-MM-DD).",
        )],
        payment_method: Annotated[Optional[str], Field(
            description="Method hint: 'cash', 'bank_transfer', 'card', etc.",
        )] = None,
        comment: Annotated[Optional[str], Field(
            description="Internal note (e.g. bank transaction reference).",
        )] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        Record a payment received against a sales document.

        For partial payments, call this multiple times with the partial amounts —
        each call adds a Payment record and updates the document's paid balance.
        """
        ensure_date(payment_date, "payment_date")
        data = drop_none({
            "Amount": amount,
            "PaymentDate": payment_date,
            "PaymentMethod": payment_method,
            "Comment": comment,
        })
        parsed = post(f"sale/{document_id}/payment", data, "Payment")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_send_sale",
        title="Email a sales document",
        annotations=WRITE_SEND,
    )
    def paytraq_send_sale(
        document_id: Annotated[int, Field(gt=0, description="DocumentID to email.")],
        email: Annotated[Optional[str], Field(
            description=(
                "Recipient email. Omit to use the client's default email on record."
            ),
        )] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        Send the sales document to the customer as a PDF attachment.

        Non-idempotent: each call actually sends another email. Use with care.
        """
        email = ensure_email(email)
        data = drop_none({"Email": email})
        parsed = post(f"sale/{document_id}/send", data, "Send")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_get_sale_pdf",
        title="Get sales document PDF",
        annotations=READ_ONLY,
    )
    def paytraq_get_sale_pdf(
        document_id: Annotated[int, Field(gt=0, description="DocumentID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Return the PDF download URL (or base64 payload) for a sales document."""
        parsed = get(f"sale/{document_id}/pdf")
        return format_single(parsed, response_format.value)

    # ── Purchase documents ────────────────────────────────────────────────────

    @mcp.tool(
        name="paytraq_list_purchases",
        title="List purchase documents",
        annotations=READ_ONLY,
    )
    def paytraq_list_purchases(
        status: Annotated[Optional[str], Field(
            description=(
                "Filter by status. One of: "
                f"{', '.join(sorted(VALID_STATUSES))}. "
                "Note: PayTraq's status filter is imprecise for outstanding "
                "balances — prefer `unpaid_only=True` to find bills that "
                "still owe money regardless of status."
            ),
        )] = None,
        date_from: Annotated[Optional[str], Field(description="Start date (YYYY-MM-DD).")] = None,
        date_till: Annotated[Optional[str], Field(description="End date (YYYY-MM-DD).")] = None,
        supplier_id: Annotated[Optional[int], Field(
            gt=0, description="Filter to one SupplierID.",
        )] = None,
        unpaid_only: Annotated[bool, Field(
            description=(
                "If True, keep only purchases with AmountDue > 0 (reliable "
                "'unpaid' filter regardless of DocumentStatus). Applied "
                "client-side; combine with a date range for efficiency."
            ),
        )] = False,
        page: Annotated[int, Field(ge=0, description="0-indexed page (100/page).")] = 0,
        reverse: Annotated[bool, Field(
            description=(
                "False (default) = newest-first ordering. True = reverse to "
                "oldest-first. NB: PayTraq's natural order is descending by "
                "DocumentDate, so `reverse=True` flips it to ascending."
            ),
        )] = False,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        List purchase documents (vendor invoices, POs).

        Typical uses:
          - unpaid_only=True → outstanding accounts payable
          - supplier_id=N → full purchase history from one vendor
          - date range → reconcile invoices for a period

        Tip: the response is capped at ~25 000 chars. If you see a
        "response shrunk from N to M items" note, narrow the date range or
        add a filter — the trimmed items still exist, they just didn't fit.
        """
        ensure_in(status, VALID_STATUSES, "status")
        ensure_date(date_from, "date_from")
        ensure_date(date_till, "date_till")

        params: dict = {"page": page}
        if status:      params["status"] = status
        if date_from:   params["date_from"] = date_from
        if date_till:   params["date_till"] = date_till
        if supplier_id: params["supplier_id"] = supplier_id
        if reverse:     params["reverse"] = "true"
        parsed = get("purchases", params)
        result = parse_list(parsed, page=page)
        if unpaid_only:
            result.items = [it for it in result.items if _is_unpaid(it)]
            result.count = len(result.items)
        return format_list(result, response_format.value)

    @mcp.tool(
        name="paytraq_get_purchase",
        title="Get a purchase document",
        annotations=READ_ONLY,
    )
    def paytraq_get_purchase(
        document_id: Annotated[int, Field(gt=0, description="Purchase DocumentID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Return full purchase document: line items, totals, supplier, payment status."""
        parsed = get(f"purchase/{document_id}")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_create_purchase",
        title="Create a purchase document",
        annotations=WRITE_ADDITIVE,
    )
    def paytraq_create_purchase(
        supplier_id: Annotated[int, Field(gt=0, description="SupplierID.")],
        document_date: Annotated[str, Field(description="Document date (YYYY-MM-DD).")],
        currency: Annotated[str, Field(description="ISO 4217 (EUR, USD, ...).")] = "EUR",
        items: Annotated[Optional[list], Field(
            description=(
                "Line items — list of dicts with keys ItemID / Qty / Price. "
                'Example: [{"ItemID": 10, "Qty": 5, "Price": 25.00}]'
            ),
        )] = None,
        ref_number: Annotated[Optional[str], Field(
            description="Supplier's invoice reference.",
        )] = None,
        due_date: Annotated[Optional[str], Field(
            description="Payment due date (YYYY-MM-DD).",
        )] = None,
        comment: Annotated[Optional[str], Field(description="Internal notes.")] = None,
        warehouse_id: Annotated[Optional[int], Field(
            gt=0, description="Destination WarehouseID for received goods.",
        )] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        Create a purchase document (vendor invoice / PO) and return its DocumentID.

        Workflow: paytraq_create_purchase → paytraq_approve_purchase →
        paytraq_post_purchase → paytraq_record_purchase_payment.
        """
        ensure_date(document_date, "document_date")
        ensure_date(due_date, "due_date")
        currency = ensure_currency(currency) or "EUR"
        line_items = _normalise_line_items(items)

        data: dict[str, Any] = drop_none({
            "SupplierID": supplier_id,
            "DocumentDate": document_date,
            "Currency": currency,
            "DocumentRef": ref_number,
            "DueDate": due_date,
            "Comment": comment,
            "WarehouseID": warehouse_id,
        })
        if line_items:
            data["LineItems"] = {"LineItem": line_items}

        parsed = post("purchases", data, "Document")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_approve_purchase",
        title="Approve a purchase document",
        annotations=WRITE_IDEMPOTENT,
    )
    def paytraq_approve_purchase(
        document_id: Annotated[int, Field(gt=0, description="Purchase DocumentID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Move a purchase document from 'draft' to 'approved'."""
        parsed = post(f"purchase/{document_id}/approve", {}, "Document")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_post_purchase",
        title="Post a purchase to the ledger",
        annotations=WRITE_IDEMPOTENT,
    )
    def paytraq_post_purchase(
        document_id: Annotated[int, Field(gt=0, description="Purchase DocumentID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Post an approved purchase document, creating the corresponding journal entries."""
        parsed = post(f"purchase/{document_id}/post", {}, "Document")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_record_purchase_payment",
        title="Record a payment to a supplier",
        annotations=WRITE_ADDITIVE,
    )
    def paytraq_record_purchase_payment(
        document_id: Annotated[int, Field(gt=0, description="Purchase DocumentID being paid.")],
        amount: Annotated[float, Field(
            gt=0, description="Payment amount (e.g. 500.00).",
        )],
        payment_date: Annotated[str, Field(
            description="Date payment was sent (YYYY-MM-DD).",
        )],
        comment: Annotated[Optional[str], Field(
            description="Internal note (e.g. bank transfer reference).",
        )] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Record a payment made to a supplier. Multiple calls allowed for partial payments."""
        ensure_date(payment_date, "payment_date")
        data = drop_none({
            "Amount": amount,
            "PaymentDate": payment_date,
            "Comment": comment,
        })
        parsed = post(f"purchase/{document_id}/payment", data, "Payment")
        return format_single(parsed, response_format.value)

    # ── Payments & attachments ────────────────────────────────────────────────

    @mcp.tool(
        name="paytraq_list_payments",
        title="List payments",
        annotations=READ_ONLY,
    )
    def paytraq_list_payments(
        date_from: Annotated[Optional[str], Field(description="Start date (YYYY-MM-DD).")] = None,
        date_till: Annotated[Optional[str], Field(description="End date (YYYY-MM-DD).")] = None,
        page: Annotated[int, Field(ge=0, description="0-indexed page (100/page).")] = 0,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """List all payment records (received from clients and sent to suppliers)."""
        ensure_date(date_from, "date_from")
        ensure_date(date_till, "date_till")

        params: dict = {"page": page}
        if date_from: params["date_from"] = date_from
        if date_till: params["date_till"] = date_till
        parsed = get("payments", params)
        return format_list(parse_list(parsed, page=page), response_format.value)

    @mcp.tool(
        name="paytraq_get_payment",
        title="Get a payment",
        annotations=READ_ONLY,
    )
    def paytraq_get_payment(
        payment_id: Annotated[int, Field(gt=0, description="Numeric PaymentID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Return full payment record: amount, date, method, linked document."""
        parsed = get(f"payment/{payment_id}")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_list_attachments",
        title="List document attachments",
        annotations=READ_ONLY,
    )
    def paytraq_list_attachments(
        document_id: Annotated[int, Field(
            gt=0, description="Sales or purchase DocumentID.",
        )],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """List file attachments on a document (scanned invoices, receipts, contracts)."""
        parsed = get(f"attachments/{document_id}")
        result = parse_list(parsed, page=0)
        return format_list(result, response_format.value)
