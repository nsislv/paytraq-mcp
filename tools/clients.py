"""
PayTraq MCP — Clients (customers), Suppliers (vendors), and Employees.

CRUD operations on the three types of business partner records PayTraq tracks.
Client = customer you invoice; Supplier = vendor you pay; Employee = internal
staff assigned to documents.
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
    ensure_country,
    ensure_currency,
    ensure_email,
)


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

    # ── Clients ───────────────────────────────────────────────────────────────

    @mcp.tool(
        name="paytraq_list_clients",
        title="List clients (customers)",
        annotations=READ_ONLY,
    )
    def paytraq_list_clients(
        query: Annotated[Optional[str], Field(
            description="Filter by client name or email. Omit to list all.",
        )] = None,
        page: Annotated[int, Field(
            ge=0, description="0-indexed page (100 records per page).",
        )] = 0,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        List clients (customers), optionally filtered by name/email.

        Use this to find a ClientID before creating an invoice, recording a
        payment, or looking up outstanding balances.
        """
        params: dict = {"page": page}
        if query:
            params["query"] = query
        parsed = get("clients", params)
        return format_list(parse_list(parsed, page=page), response_format.value)

    @mcp.tool(
        name="paytraq_get_client",
        title="Get client details",
        annotations=READ_ONLY,
    )
    def paytraq_get_client(
        client_id: Annotated[int, Field(gt=0, description="Numeric PayTraq ClientID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        Retrieve the full client record: address, VAT number, currency, contacts.
        Use when you need more detail than the listing provides.
        """
        parsed = get(f"client/{client_id}")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_create_client",
        title="Create a client",
        annotations=WRITE_ADDITIVE,
    )
    def paytraq_create_client(
        name: Annotated[str, Field(min_length=1, description="Full name or company name.")],
        email: Annotated[Optional[str], Field(
            description="Email for invoicing/communication.",
        )] = None,
        phone: Annotated[Optional[str], Field(
            description="Phone number including country code.",
        )] = None,
        reg_number: Annotated[Optional[str], Field(
            description="Company registration number.",
        )] = None,
        vat_number: Annotated[Optional[str], Field(
            description="VAT registration number (e.g. LV40003...).",
        )] = None,
        country: Annotated[Optional[str], Field(
            description="2-letter ISO 3166-1 alpha-2 country code (LV, EE, DE...).",
        )] = None,
        address: Annotated[Optional[str], Field(description="Street address.")] = None,
        city: Annotated[Optional[str], Field(description="City.")] = None,
        zip_code: Annotated[Optional[str], Field(description="Postal/ZIP code.")] = None,
        client_type: Annotated[int, Field(
            ge=1, le=2,
            description="1 = Individual (natural person), 2 = Company (legal entity).",
        )] = 2,
        currency: Annotated[Optional[str], Field(
            description="Default billing currency (ISO 4217: EUR, USD...).",
        )] = None,
        comment: Annotated[Optional[str], Field(
            description="Internal-only notes about the client.",
        )] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        Create a new client record and return its ClientID.

        Typical flow: call this before issuing the first invoice to a new
        customer. The returned ClientID is required by paytraq_create_sale.
        """
        email = ensure_email(email)
        country = ensure_country(country)
        currency = ensure_currency(currency)

        data = drop_none({
            "Name": name,
            "Type": client_type,
            "Email": email,
            "Phone": phone,
            "RegNumber": reg_number,
            "VatNumber": vat_number,
            "Country": country,
            "Address": address,
            "City": city,
            "Zip": zip_code,
            "Currency": currency,
            "Comment": comment,
        })
        parsed = post("client", data, "Client")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_update_client",
        title="Update a client",
        annotations=WRITE_UPDATE,
    )
    def paytraq_update_client(
        client_id: Annotated[int, Field(gt=0, description="ClientID to update.")],
        name: Annotated[Optional[str], Field(description="New name.")] = None,
        email: Annotated[Optional[str], Field(description="New email.")] = None,
        phone: Annotated[Optional[str], Field(description="New phone.")] = None,
        reg_number: Annotated[Optional[str], Field(description="New registration number.")] = None,
        vat_number: Annotated[Optional[str], Field(description="New VAT number.")] = None,
        country: Annotated[Optional[str], Field(description="New 2-letter country code.")] = None,
        address: Annotated[Optional[str], Field(description="New street address.")] = None,
        city: Annotated[Optional[str], Field(description="New city.")] = None,
        zip_code: Annotated[Optional[str], Field(description="New postal code.")] = None,
        comment: Annotated[Optional[str], Field(description="New internal notes.")] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        Update one or more fields on an existing client. Omitted fields are preserved.

        Provide at least one field to change; empty update requests are rejected
        so you don't accidentally wipe data.
        """
        email = ensure_email(email)
        country = ensure_country(country)

        data = drop_none({
            "Name": name,
            "Email": email,
            "Phone": phone,
            "RegNumber": reg_number,
            "VatNumber": vat_number,
            "Country": country,
            "Address": address,
            "City": city,
            "Zip": zip_code,
            "Comment": comment,
        })
        if not data:
            raise PaytraqBadRequest(
                "No fields supplied — pass at least one of name/email/phone/... to update."
            )
        parsed = post(f"client/{client_id}", data, "Client")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_get_client_outstanding",
        title="Get client outstanding balance",
        annotations=READ_ONLY,
    )
    def paytraq_get_client_outstanding(
        client_id: Annotated[int, Field(gt=0, description="ClientID to check.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """
        Return a client's unpaid invoices and total amount owed.

        Use before extending credit, sending reminders, or answering 'how much
        does customer X owe us?'.
        """
        parsed = get(f"client/outstanding/{client_id}")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_list_client_contacts",
        title="List contacts of a client",
        annotations=READ_ONLY,
    )
    def paytraq_list_client_contacts(
        client_id: Annotated[int, Field(gt=0, description="ClientID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """List contact persons associated with a client (AP, procurement, etc.)."""
        parsed = get(f"client/contacts/{client_id}")
        result = parse_list(parsed, page=0)
        return format_list(result, response_format.value)

    @mcp.tool(
        name="paytraq_add_client_contact",
        title="Add a contact to a client",
        annotations=WRITE_ADDITIVE,
    )
    def paytraq_add_client_contact(
        client_id: Annotated[int, Field(gt=0, description="ClientID to attach to.")],
        name: Annotated[str, Field(min_length=1, description="Contact person's full name.")],
        email: Annotated[Optional[str], Field(description="Contact email.")] = None,
        phone: Annotated[Optional[str], Field(description="Contact phone.")] = None,
        position: Annotated[Optional[str], Field(
            description="Job title (e.g. 'CFO', 'Accountant').",
        )] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Attach a new contact person to an existing client."""
        email = ensure_email(email)
        data = drop_none({
            "Name": name, "Email": email, "Phone": phone, "Position": position,
        })
        parsed = post(f"client/contact/{client_id}", data, "Contact")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_list_client_banks",
        title="List client bank accounts",
        annotations=READ_ONLY,
    )
    def paytraq_list_client_banks(
        client_id: Annotated[int, Field(gt=0, description="ClientID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Return IBAN / BIC / bank name for a client's bank accounts."""
        parsed = get(f"client/banks/{client_id}")
        result = parse_list(parsed, page=0)
        return format_list(result, response_format.value)

    @mcp.tool(
        name="paytraq_list_client_groups",
        title="List client groups",
        annotations=READ_ONLY,
    )
    def paytraq_list_client_groups(
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """List configured client groups (categories/segments)."""
        parsed = get("clientGroups")
        result = parse_list(parsed, page=0)
        return format_list(result, response_format.value)

    # ── Suppliers ─────────────────────────────────────────────────────────────

    @mcp.tool(
        name="paytraq_list_suppliers",
        title="List suppliers (vendors)",
        annotations=READ_ONLY,
    )
    def paytraq_list_suppliers(
        query: Annotated[Optional[str], Field(
            description="Filter by supplier name or email.",
        )] = None,
        page: Annotated[int, Field(ge=0, description="0-indexed page (100/page).")] = 0,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """List suppliers. Use to find a SupplierID before creating a purchase."""
        params: dict = {"page": page}
        if query:
            params["query"] = query
        parsed = get("suppliers", params)
        return format_list(parse_list(parsed, page=page), response_format.value)

    @mcp.tool(
        name="paytraq_get_supplier",
        title="Get supplier details",
        annotations=READ_ONLY,
    )
    def paytraq_get_supplier(
        supplier_id: Annotated[int, Field(gt=0, description="Numeric SupplierID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Return full supplier record: registration, VAT, address, bank details."""
        parsed = get(f"supplier/{supplier_id}")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_create_supplier",
        title="Create a supplier",
        annotations=WRITE_ADDITIVE,
    )
    def paytraq_create_supplier(
        name: Annotated[str, Field(min_length=1, description="Supplier company name.")],
        email: Annotated[Optional[str], Field(description="Supplier email.")] = None,
        phone: Annotated[Optional[str], Field(description="Supplier phone.")] = None,
        reg_number: Annotated[Optional[str], Field(description="Company registration number.")] = None,
        vat_number: Annotated[Optional[str], Field(description="VAT number.")] = None,
        country: Annotated[Optional[str], Field(description="2-letter ISO country code.")] = None,
        address: Annotated[Optional[str], Field(description="Street address.")] = None,
        currency: Annotated[Optional[str], Field(description="ISO 4217 default purchase currency.")] = None,
        comment: Annotated[Optional[str], Field(description="Internal notes.")] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Create a supplier record. Call before the first purchase from a new vendor."""
        email = ensure_email(email)
        country = ensure_country(country)
        currency = ensure_currency(currency)

        data = drop_none({
            "Name": name,
            "Email": email,
            "Phone": phone,
            "RegNumber": reg_number,
            "VatNumber": vat_number,
            "Country": country,
            "Address": address,
            "Currency": currency,
            "Comment": comment,
        })
        parsed = post("supplier", data, "Supplier")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_update_supplier",
        title="Update a supplier",
        annotations=WRITE_UPDATE,
    )
    def paytraq_update_supplier(
        supplier_id: Annotated[int, Field(gt=0, description="SupplierID to update.")],
        name: Annotated[Optional[str], Field(description="New name.")] = None,
        email: Annotated[Optional[str], Field(description="New email.")] = None,
        phone: Annotated[Optional[str], Field(description="New phone.")] = None,
        reg_number: Annotated[Optional[str], Field(description="New registration number.")] = None,
        vat_number: Annotated[Optional[str], Field(description="New VAT number.")] = None,
        country: Annotated[Optional[str], Field(description="New country code.")] = None,
        address: Annotated[Optional[str], Field(description="New address.")] = None,
        comment: Annotated[Optional[str], Field(description="New internal notes.")] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Update fields on an existing supplier. Omitted fields unchanged."""
        email = ensure_email(email)
        country = ensure_country(country)

        data = drop_none({
            "Name": name,
            "Email": email,
            "Phone": phone,
            "RegNumber": reg_number,
            "VatNumber": vat_number,
            "Country": country,
            "Address": address,
            "Comment": comment,
        })
        if not data:
            raise PaytraqBadRequest(
                "No fields supplied — pass at least one of name/email/phone/... to update."
            )
        parsed = post(f"supplier/{supplier_id}", data, "Supplier")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_list_supplier_groups",
        title="List supplier groups",
        annotations=READ_ONLY,
    )
    def paytraq_list_supplier_groups(
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """List configured supplier groups (categories)."""
        parsed = get("supplierGroups")
        result = parse_list(parsed, page=0)
        return format_list(result, response_format.value)

    # ── Employees ─────────────────────────────────────────────────────────────

    @mcp.tool(
        name="paytraq_list_employees",
        title="List employees",
        annotations=READ_ONLY,
    )
    def paytraq_list_employees(
        query: Annotated[Optional[str], Field(
            description="Filter by employee name.",
        )] = None,
        page: Annotated[int, Field(ge=0, description="0-indexed page (100/page).")] = 0,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """List employees. Use to find EmployeeIDs when assigning them to documents."""
        params: dict = {"page": page}
        if query:
            params["query"] = query
        parsed = get("employees", params)
        return format_list(parse_list(parsed, page=page), response_format.value)

    @mcp.tool(
        name="paytraq_get_employee",
        title="Get employee details",
        annotations=READ_ONLY,
    )
    def paytraq_get_employee(
        employee_id: Annotated[int, Field(gt=0, description="Numeric EmployeeID.")],
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Return full employee record: contact info, position, department."""
        parsed = get(f"employee/{employee_id}")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_create_employee",
        title="Create an employee",
        annotations=WRITE_ADDITIVE,
    )
    def paytraq_create_employee(
        name: Annotated[str, Field(min_length=1, description="Employee full name.")],
        email: Annotated[Optional[str], Field(description="Work email address.")] = None,
        phone: Annotated[Optional[str], Field(description="Phone number.")] = None,
        position: Annotated[Optional[str], Field(
            description="Job title (e.g. 'Accountant', 'Sales Manager').",
        )] = None,
        comment: Annotated[Optional[str], Field(description="Internal notes.")] = None,
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """Create a new employee record for the accounting system."""
        email = ensure_email(email)
        data = drop_none({
            "Name": name,
            "Email": email,
            "Phone": phone,
            "Position": position,
            "Comment": comment,
        })
        parsed = post("employee", data, "Employee")
        return format_single(parsed, response_format.value)

    @mcp.tool(
        name="paytraq_list_employee_groups",
        title="List employee groups",
        annotations=READ_ONLY,
    )
    def paytraq_list_employee_groups(
        response_format: Annotated[ResponseFormat, Field(
            description="'json' or 'markdown'.",
        )] = ResponseFormat.JSON,
    ) -> str:
        """List configured employee groups / departments."""
        parsed = get("employeeGroups")
        result = parse_list(parsed, page=0)
        return format_list(result, response_format.value)
