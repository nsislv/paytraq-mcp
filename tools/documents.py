"""
PayTraq MCP — Sales & Purchase Documents Tools
------------------------------------------------
Tools for managing sales documents (invoices, orders, receipts, credit notes),
purchase documents (vendor orders and invoices), payments, and attachments.

When to use these tools:
  - list_sales / get_sale: browse or retrieve customer invoices and orders
  - create_sale: issue a new invoice, sales order, or receipt to a client
  - approve_sale / post_sale: move a draft through the accounting workflow
  - record_sale_payment: mark an invoice as paid
  - send_sale: email an invoice directly to a client
  - list_purchases / create_purchase: manage vendor invoices and purchase orders
  - list_payments: review all incoming/outgoing payment records
"""

import re
from typing import Annotated, Optional
from pydantic import Field
from mcp.server.fastmcp import FastMCP
from paytraq_client import get, post, format_response

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

VALID_SALE_STATUSES = {"draft", "approved", "posted", "paid", "voided"}
VALID_SALE_TYPES = {"sales_invoice", "sales_order", "sales_proforma", "sales_receipt", "credit_note"}
VALID_OPERATIONS = {"sell_goods", "sell_services", "other_income"}


def _validate_date(value: Optional[str], field_name: str) -> Optional[str]:
    if value and not _DATE_RE.match(value):
        return f"Invalid {field_name} format '{value}'. Use YYYY-MM-DD (e.g. 2026-01-31)."
    return None


def register(mcp: FastMCP) -> None:

    # ── SALES DOCUMENTS ───────────────────────────────────────────────────────

    @mcp.tool()
    def list_sales(
        status: Annotated[Optional[str], Field(
            default=None,
            description=(
                "Filter by document status. "
                "Valid values: draft, approved, posted, paid, voided."
            ),
        )] = None,
        date_from: Annotated[Optional[str], Field(
            default=None,
            description="Start date filter in YYYY-MM-DD format (e.g. 2026-01-01).",
        )] = None,
        date_till: Annotated[Optional[str], Field(
            default=None,
            description="End date filter in YYYY-MM-DD format (e.g. 2026-12-31).",
        )] = None,
        client_id: Annotated[Optional[int], Field(
            default=None,
            description="Filter to only show documents for this client ID.",
            gt=0,
        )] = None,
        query: Annotated[Optional[str], Field(
            default=None,
            description="Text search by document number or reference.",
        )] = None,
        page: Annotated[int, Field(
            default=0,
            ge=0,
            description="Page number for pagination (100 records per page).",
        )] = 0,
        reverse: Annotated[bool, Field(
            default=False,
            description="Set True to sort results newest-first (descending by date).",
        )] = False,
    ) -> str:
        """
        List sales documents (invoices, orders, receipts, credit notes) in PayTraq.

        Use this tool when you need to:
        - Review all unpaid invoices (status=approved or posted)
        - Find invoices for a specific client
        - Check recent sales activity for a date range
        - Look up a document by number
        """
        try:
            if status and status not in VALID_SALE_STATUSES:
                return (
                    f"Error: Invalid status '{status}'. "
                    f"Valid values: {', '.join(sorted(VALID_SALE_STATUSES))}."
                )
            for val, name in [(date_from, "date_from"), (date_till, "date_till")]:
                err = _validate_date(val, name)
                if err:
                    return f"Error: {err}"

            params: dict = {"page": page}
            if status:    params["status"] = status
            if date_from: params["date_from"] = date_from
            if date_till: params["date_till"] = date_till
            if client_id: params["client_id"] = client_id
            if query:     params["query"] = query
            if reverse:   params["reverse"] = "true"
            return format_response(get("sales", params))
        except Exception as e:
            raise

    @mcp.tool()
    def get_sale(
        document_id: Annotated[int, Field(
            description="Numeric PayTraq sales document ID.",
            gt=0,
        )],
    ) -> str:
        """
        Get full details of a sales document (invoice, order, receipt) by ID.

        Use this tool when you need line items, amounts, due date, payment status,
        or client details for a specific document.
        """
        try:
            return format_response(get(f"sale/{document_id}"))
        except Exception as e:
            raise

    @mcp.tool()
    def create_sale(
        client_id: Annotated[int, Field(
            description="PayTraq client ID to invoice. Use list_clients to find it.",
            gt=0,
        )],
        document_date: Annotated[str, Field(
            description="Document date in YYYY-MM-DD format (e.g. 2026-01-15).",
        )],
        sale_type: Annotated[str, Field(
            default="sales_invoice",
            description=(
                "Document type: sales_invoice (standard invoice), sales_order, "
                "sales_proforma (pro-forma), sales_receipt, credit_note."
            ),
        )] = "sales_invoice",
        operation: Annotated[str, Field(
            default="sell_goods",
            description=(
                "Revenue type: sell_goods (product sale), "
                "sell_services (service delivery), other_income."
            ),
        )] = "sell_goods",
        currency: Annotated[str, Field(
            default="EUR",
            description="ISO 4217 currency code for the document (e.g. EUR, USD).",
        )] = "EUR",
        items: Annotated[Optional[list], Field(
            default=None,
            description=(
                "Line items for the document. Each item is a dict with keys: "
                "ItemID (int), Qty (float), Price (float). "
                "Example: [{\"ItemID\": 42, \"Qty\": 2, \"Price\": 150.00}]"
            ),
        )] = None,
        ref_number: Annotated[Optional[str], Field(
            default=None,
            description="Custom document reference number (e.g. your PO number).",
        )] = None,
        due_date: Annotated[Optional[str], Field(
            default=None,
            description="Payment due date in YYYY-MM-DD format.",
        )] = None,
        comment: Annotated[Optional[str], Field(
            default=None,
            description="Notes or memo printed on the document.",
        )] = None,
        warehouse_id: Annotated[Optional[int], Field(
            default=None,
            description="Source warehouse ID for goods. Use list_warehouses to find it.",
            gt=0,
        )] = None,
    ) -> str:
        """
        Create a new sales document (invoice, order, receipt, etc.) in PayTraq.

        Use this tool when:
        - Issuing a new invoice to a customer
        - Creating a pro-forma invoice for approval
        - Recording a cash sale receipt
        - Issuing a credit note for a return

        After creation, use approve_sale and post_sale to move it through the workflow,
        then record_sale_payment when the client pays.
        """
        try:
            err = _validate_date(document_date, "document_date")
            if err:
                return f"Error: {err}"
            err = _validate_date(due_date, "due_date")
            if err:
                return f"Error: {err}"
            if sale_type not in VALID_SALE_TYPES:
                return (
                    f"Error: Invalid sale_type '{sale_type}'. "
                    f"Valid values: {', '.join(sorted(VALID_SALE_TYPES))}."
                )
            if operation not in VALID_OPERATIONS:
                return (
                    f"Error: Invalid operation '{operation}'. "
                    f"Valid values: {', '.join(sorted(VALID_OPERATIONS))}."
                )

            data: dict = {
                "ClientID": client_id,
                "DocumentDate": document_date,
                "SaleType": sale_type,
                "Operation": operation,
                "Currency": currency.upper(),
            }
            if ref_number:    data["DocumentRef"] = ref_number
            if due_date:      data["DueDate"] = due_date
            if comment:       data["Comment"] = comment
            if warehouse_id:  data["WarehouseID"] = warehouse_id
            if items:         data["LineItems"] = {"LineItem": items}

            return format_response(post("sales", data, "Document"))
        except Exception as e:
            raise

    @mcp.tool()
    def approve_sale(
        document_id: Annotated[int, Field(
            description="ID of the sales document to approve.",
            gt=0,
        )],
    ) -> str:
        """
        Approve a sales document, moving it from 'draft' to 'approved' status.

        Use this tool after creating a draft invoice and it has been reviewed.
        Once approved, the document can be sent to the client or posted to accounting.
        """
        try:
            return format_response(post(f"sale/{document_id}/approve", {}, "Document"))
        except Exception as e:
            raise

    @mcp.tool()
    def post_sale(
        document_id: Annotated[int, Field(
            description="ID of the sales document to post to accounting.",
            gt=0,
        )],
    ) -> str:
        """
        Post a sales document to the accounting ledger ('posted' status).

        Use this tool after approving an invoice to record it as a formal
        accounting entry. This creates journal entries in the general ledger.
        """
        try:
            return format_response(post(f"sale/{document_id}/post", {}, "Document"))
        except Exception as e:
            raise

    @mcp.tool()
    def void_sale(
        document_id: Annotated[int, Field(
            description="ID of the sales document to void/cancel.",
            gt=0,
        )],
    ) -> str:
        """
        Void (cancel) a sales document. This action cannot be undone.

        Use this tool when a document was created in error or needs to be cancelled.
        Use a credit_note instead if you need to reverse a posted invoice properly.
        """
        try:
            return format_response(post(f"sale/{document_id}/void", {}, "Document"))
        except Exception as e:
            raise

    @mcp.tool()
    def record_sale_payment(
        document_id: Annotated[int, Field(
            description="ID of the sales document being paid.",
            gt=0,
        )],
        amount: Annotated[float, Field(
            description="Payment amount. Use dot as decimal separator (e.g. 150.00).",
            gt=0,
        )],
        payment_date: Annotated[str, Field(
            description="Date the payment was received, in YYYY-MM-DD format.",
        )],
        payment_method: Annotated[Optional[str], Field(
            default=None,
            description="Payment method (e.g. 'cash', 'bank_transfer', 'card').",
        )] = None,
        comment: Annotated[Optional[str], Field(
            default=None,
            description="Internal note about this payment (e.g. bank transaction ID).",
        )] = None,
    ) -> str:
        """
        Record a payment received against a sales invoice or document.

        Use this tool when a customer has paid an invoice. For partial payments,
        call this tool multiple times with the partial amounts.
        """
        try:
            err = _validate_date(payment_date, "payment_date")
            if err:
                return f"Error: {err}"

            data: dict = {
                "Amount": amount,
                "PaymentDate": payment_date,
            }
            if payment_method: data["PaymentMethod"] = payment_method
            if comment:        data["Comment"] = comment
            return format_response(post(f"sale/{document_id}/payment", data, "Payment"))
        except Exception as e:
            raise

    @mcp.tool()
    def send_sale(
        document_id: Annotated[int, Field(
            description="ID of the sales document to send by email.",
            gt=0,
        )],
        email: Annotated[Optional[str], Field(
            default=None,
            description=(
                "Recipient email address. If omitted, PayTraq uses the client's "
                "default email on record."
            ),
        )] = None,
    ) -> str:
        """
        Send a sales document to the client by email.

        Use this tool after approving or posting an invoice to deliver it
        to the customer. PayTraq sends a PDF attachment.
        """
        try:
            if email and not _EMAIL_RE.match(email):
                return f"Error: Invalid email address '{email}'."
            data: dict = {}
            if email: data["Email"] = email
            return format_response(post(f"sale/{document_id}/send", data, "Send"))
        except Exception as e:
            raise

    @mcp.tool()
    def get_sale_pdf(
        document_id: Annotated[int, Field(
            description="ID of the sales document to get PDF data for.",
            gt=0,
        )],
    ) -> str:
        """
        Get the PDF download URL or base64 content for a sales document.

        Use this tool when you need to download or share the PDF version of an
        invoice. Returns the URL or encoded PDF data from the PayTraq API.
        """
        try:
            return format_response(get(f"sale/{document_id}/pdf"))
        except Exception as e:
            raise

    # ── PURCHASES ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_purchases(
        status: Annotated[Optional[str], Field(
            default=None,
            description=(
                "Filter by document status. "
                "Valid values: draft, approved, posted, paid, voided."
            ),
        )] = None,
        date_from: Annotated[Optional[str], Field(
            default=None,
            description="Start date filter in YYYY-MM-DD format.",
        )] = None,
        date_till: Annotated[Optional[str], Field(
            default=None,
            description="End date filter in YYYY-MM-DD format.",
        )] = None,
        supplier_id: Annotated[Optional[int], Field(
            default=None,
            description="Filter to only show documents from this supplier ID.",
            gt=0,
        )] = None,
        page: Annotated[int, Field(
            default=0,
            ge=0,
            description="Page number (100 records per page).",
        )] = 0,
        reverse: Annotated[bool, Field(
            default=False,
            description="Set True to sort results newest-first.",
        )] = False,
    ) -> str:
        """
        List purchase documents (vendor invoices, purchase orders) in PayTraq.

        Use this tool when you need to:
        - Review unpaid vendor invoices
        - Check purchase history from a specific supplier
        - Reconcile incoming invoices for a date range
        """
        try:
            if status and status not in VALID_SALE_STATUSES:
                return (
                    f"Error: Invalid status '{status}'. "
                    f"Valid values: {', '.join(sorted(VALID_SALE_STATUSES))}."
                )
            for val, name in [(date_from, "date_from"), (date_till, "date_till")]:
                err = _validate_date(val, name)
                if err:
                    return f"Error: {err}"

            params: dict = {"page": page}
            if status:      params["status"] = status
            if date_from:   params["date_from"] = date_from
            if date_till:   params["date_till"] = date_till
            if supplier_id: params["supplier_id"] = supplier_id
            if reverse:     params["reverse"] = "true"
            return format_response(get("purchases", params))
        except Exception as e:
            raise

    @mcp.tool()
    def get_purchase(
        document_id: Annotated[int, Field(
            description="Numeric PayTraq purchase document ID.",
            gt=0,
        )],
    ) -> str:
        """
        Get full details of a purchase document (vendor invoice or order) by ID.

        Use this tool to see line items, amounts, supplier details, and payment
        status for a specific purchase document.
        """
        try:
            return format_response(get(f"purchase/{document_id}"))
        except Exception as e:
            raise

    @mcp.tool()
    def create_purchase(
        supplier_id: Annotated[int, Field(
            description="PayTraq supplier ID. Use list_suppliers to find it.",
            gt=0,
        )],
        document_date: Annotated[str, Field(
            description="Document date in YYYY-MM-DD format.",
        )],
        currency: Annotated[str, Field(
            default="EUR",
            description="ISO 4217 currency code (e.g. EUR, USD).",
        )] = "EUR",
        items: Annotated[Optional[list], Field(
            default=None,
            description=(
                "Line items list. Each item is a dict with keys: "
                "ItemID (int), Qty (float), Price (float). "
                "Example: [{\"ItemID\": 10, \"Qty\": 5, \"Price\": 25.00}]"
            ),
        )] = None,
        ref_number: Annotated[Optional[str], Field(
            default=None,
            description="Supplier's invoice reference number.",
        )] = None,
        due_date: Annotated[Optional[str], Field(
            default=None,
            description="Payment due date in YYYY-MM-DD format.",
        )] = None,
        comment: Annotated[Optional[str], Field(
            default=None,
            description="Internal notes about this purchase.",
        )] = None,
        warehouse_id: Annotated[Optional[int], Field(
            default=None,
            description="Destination warehouse ID for received goods.",
            gt=0,
        )] = None,
    ) -> str:
        """
        Create a new purchase document (vendor invoice or purchase order) in PayTraq.

        Use this tool when recording an invoice received from a supplier.
        After creation, use approve_purchase and post_purchase to complete the
        accounting workflow, then record_purchase_payment when you pay the vendor.
        """
        try:
            err = _validate_date(document_date, "document_date")
            if err:
                return f"Error: {err}"
            err = _validate_date(due_date, "due_date")
            if err:
                return f"Error: {err}"

            data: dict = {
                "SupplierID": supplier_id,
                "DocumentDate": document_date,
                "Currency": currency.upper(),
            }
            if ref_number:   data["DocumentRef"] = ref_number
            if due_date:     data["DueDate"] = due_date
            if comment:      data["Comment"] = comment
            if warehouse_id: data["WarehouseID"] = warehouse_id
            if items:        data["LineItems"] = {"LineItem": items}

            return format_response(post("purchases", data, "Document"))
        except Exception as e:
            raise

    @mcp.tool()
    def approve_purchase(
        document_id: Annotated[int, Field(
            description="ID of the purchase document to approve.",
            gt=0,
        )],
    ) -> str:
        """
        Approve a purchase document, moving it from 'draft' to 'approved' status.

        Use this tool after reviewing a vendor invoice draft before posting it
        to the accounting ledger.
        """
        try:
            return format_response(post(f"purchase/{document_id}/approve", {}, "Document"))
        except Exception as e:
            raise

    @mcp.tool()
    def post_purchase(
        document_id: Annotated[int, Field(
            description="ID of the purchase document to post to accounting.",
            gt=0,
        )],
    ) -> str:
        """
        Post a purchase document to the accounting ledger ('posted' status).

        Use this tool after approving a vendor invoice to create the corresponding
        journal entries in the general ledger.
        """
        try:
            return format_response(post(f"purchase/{document_id}/post", {}, "Document"))
        except Exception as e:
            raise

    @mcp.tool()
    def record_purchase_payment(
        document_id: Annotated[int, Field(
            description="ID of the purchase document being paid.",
            gt=0,
        )],
        amount: Annotated[float, Field(
            description="Payment amount. Use dot as decimal separator (e.g. 500.00).",
            gt=0,
        )],
        payment_date: Annotated[str, Field(
            description="Date the payment was sent, in YYYY-MM-DD format.",
        )],
        comment: Annotated[Optional[str], Field(
            default=None,
            description="Internal note (e.g. bank transfer reference).",
        )] = None,
    ) -> str:
        """
        Record a payment made to a supplier for a purchase document.

        Use this tool when you have paid a vendor invoice. For partial payments,
        call this tool multiple times with the respective partial amounts.
        """
        try:
            err = _validate_date(payment_date, "payment_date")
            if err:
                return f"Error: {err}"

            data: dict = {"Amount": amount, "PaymentDate": payment_date}
            if comment: data["Comment"] = comment
            return format_response(post(f"purchase/{document_id}/payment", data, "Payment"))
        except Exception as e:
            raise

    # ── PAYMENTS ──────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_payments(
        date_from: Annotated[Optional[str], Field(
            default=None,
            description="Start date filter in YYYY-MM-DD format.",
        )] = None,
        date_till: Annotated[Optional[str], Field(
            default=None,
            description="End date filter in YYYY-MM-DD format.",
        )] = None,
        page: Annotated[int, Field(
            default=0,
            ge=0,
            description="Page number (100 records per page).",
        )] = 0,
    ) -> str:
        """
        List all payment records (both received from clients and sent to suppliers).

        Use this tool when you need a cash-flow view of all money movements,
        or to reconcile bank statements with PayTraq payment records.
        """
        try:
            for val, name in [(date_from, "date_from"), (date_till, "date_till")]:
                err = _validate_date(val, name)
                if err:
                    return f"Error: {err}"

            params: dict = {"page": page}
            if date_from: params["date_from"] = date_from
            if date_till: params["date_till"] = date_till
            return format_response(get("payments", params))
        except Exception as e:
            raise

    @mcp.tool()
    def get_payment(
        payment_id: Annotated[int, Field(
            description="Numeric PayTraq payment ID.",
            gt=0,
        )],
    ) -> str:
        """
        Get full details of a payment record by ID.

        Use this tool when you need to verify the amount, date, method, and
        linked document for a specific payment transaction.
        """
        try:
            return format_response(get(f"payment/{payment_id}"))
        except Exception as e:
            raise

    # ── ATTACHMENTS ───────────────────────────────────────────────────────────

    @mcp.tool()
    def list_attachments(
        document_id: Annotated[int, Field(
            description=(
                "ID of the sales or purchase document whose attachments to list."
            ),
            gt=0,
        )],
    ) -> str:
        """
        List all file attachments on a sales or purchase document.

        Use this tool when you need to check whether a document has scanned
        invoices, receipts, or other supporting files attached.
        """
        try:
            return format_response(get(f"attachments/{document_id}"))
        except Exception as e:
            raise
