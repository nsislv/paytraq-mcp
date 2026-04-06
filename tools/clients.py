"""
PayTraq MCP — Clients, Suppliers & Employees Tools
----------------------------------------------------
Tools for managing clients (customers), suppliers (vendors), and employees
in PayTraq.

When to use these tools:
  - list_clients / get_client: look up customer information, find client IDs
  - create_client / update_client: onboard new customers or update their data
  - get_client_outstanding: check how much a customer owes
  - list_suppliers / create_supplier: manage vendor/supplier records
  - list_employees / create_employee: manage employee directory
"""

import re
from typing import Annotated, Optional
from pydantic import Field
from mcp.server.fastmcp import FastMCP
from paytraq_client import get, post, format_response

# Regex for basic email validation
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Regex for 2-letter ISO country code
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
# Regex for ISO 4217 currency code
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


def _validate_country(country: Optional[str]) -> Optional[str]:
    if country and not _COUNTRY_RE.match(country.upper()):
        return f"Invalid country code '{country}'. Use 2-letter ISO code (e.g. LV, EE, LT, DE)."
    return None


def _validate_currency(currency: Optional[str]) -> Optional[str]:
    if currency and not _CURRENCY_RE.match(currency.upper()):
        return f"Invalid currency code '{currency}'. Use 3-letter ISO 4217 code (e.g. EUR, USD, GBP)."
    return None


def register(mcp: FastMCP) -> None:

    # ── CLIENTS ───────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_clients(
        query: Annotated[Optional[str], Field(
            default=None,
            description="Filter by client name or email. Leave empty to list all clients."
        )] = None,
        page: Annotated[int, Field(
            default=0,
            ge=0,
            description="Page number for pagination (100 records per page, starting at 0)."
        )] = 0,
    ) -> str:
        """
        List all clients (customers) in PayTraq, optionally filtering by name or email.

        Use this tool when you need to:
        - Find a client's ID before creating an invoice or payment
        - Browse all customers in the system
        - Search for a specific customer by name
        """
        try:
            params = {"page": page}
            if query:
                params["query"] = query
            return format_response(get("clients", params))
        except Exception as e:
            raise

    @mcp.tool()
    def get_client(
        client_id: Annotated[int, Field(
            description="Numeric PayTraq client ID. Use list_clients to find it.",
            gt=0,
        )],
    ) -> str:
        """
        Get full details of a single client by their PayTraq ID.

        Use this tool when you need the complete client record including address,
        VAT number, currency, and contact details.
        """
        try:
            return format_response(get(f"client/{client_id}"))
        except Exception as e:
            raise

    @mcp.tool()
    def create_client(
        name: Annotated[str, Field(description="Full name or company name of the client.")],
        email: Annotated[Optional[str], Field(
            default=None,
            description="Email address for invoicing and communication."
        )] = None,
        phone: Annotated[Optional[str], Field(
            default=None,
            description="Phone number including country code."
        )] = None,
        reg_number: Annotated[Optional[str], Field(
            default=None,
            description="Company registration number."
        )] = None,
        vat_number: Annotated[Optional[str], Field(
            default=None,
            description="VAT (PVN) registration number."
        )] = None,
        country: Annotated[Optional[str], Field(
            default=None,
            description="2-letter ISO country code (e.g. LV, EE, LT, DE)."
        )] = None,
        address: Annotated[Optional[str], Field(
            default=None,
            description="Street address."
        )] = None,
        city: Annotated[Optional[str], Field(
            default=None,
            description="City name."
        )] = None,
        zip_code: Annotated[Optional[str], Field(
            default=None,
            description="Postal/ZIP code."
        )] = None,
        client_type: Annotated[int, Field(
            default=2,
            description="Client type: 1 = Individual (physical person), 2 = Company (legal entity).",
            ge=1,
            le=2,
        )] = 2,
        currency: Annotated[Optional[str], Field(
            default=None,
            description="Default invoice currency, ISO 4217 code (e.g. EUR, USD)."
        )] = None,
        comment: Annotated[Optional[str], Field(
            default=None,
            description="Internal notes or comments about the client."
        )] = None,
    ) -> str:
        """
        Create a new client (customer) record in PayTraq.

        Use this tool when onboarding a new customer before creating their first invoice.
        After creation, use the returned client ID for all subsequent documents.
        """
        try:
            if email and not _EMAIL_RE.match(email):
                return f"Error: Invalid email address '{email}'."
            if country:
                err = _validate_country(country)
                if err:
                    return f"Error: {err}"
                country = country.upper()
            if currency:
                err = _validate_currency(currency)
                if err:
                    return f"Error: {err}"
                currency = currency.upper()

            data: dict = {"Name": name, "Type": client_type}
            if email:       data["Email"] = email
            if phone:       data["Phone"] = phone
            if reg_number:  data["RegNumber"] = reg_number
            if vat_number:  data["VatNumber"] = vat_number
            if country:     data["Country"] = country
            if address:     data["Address"] = address
            if city:        data["City"] = city
            if zip_code:    data["Zip"] = zip_code
            if currency:    data["Currency"] = currency
            if comment:     data["Comment"] = comment
            return format_response(post("client", data, "Client"))
        except Exception as e:
            raise

    @mcp.tool()
    def update_client(
        client_id: Annotated[int, Field(
            description="ID of the client to update. Use list_clients to find it.",
            gt=0,
        )],
        name: Annotated[Optional[str], Field(
            default=None,
            description="New full name or company name."
        )] = None,
        email: Annotated[Optional[str], Field(
            default=None,
            description="New email address."
        )] = None,
        phone: Annotated[Optional[str], Field(
            default=None,
            description="New phone number."
        )] = None,
        reg_number: Annotated[Optional[str], Field(
            default=None,
            description="Updated company registration number."
        )] = None,
        vat_number: Annotated[Optional[str], Field(
            default=None,
            description="Updated VAT registration number."
        )] = None,
        country: Annotated[Optional[str], Field(
            default=None,
            description="2-letter ISO country code."
        )] = None,
        address: Annotated[Optional[str], Field(
            default=None,
            description="Updated street address."
        )] = None,
        city: Annotated[Optional[str], Field(
            default=None,
            description="Updated city."
        )] = None,
        zip_code: Annotated[Optional[str], Field(
            default=None,
            description="Updated postal/ZIP code."
        )] = None,
        comment: Annotated[Optional[str], Field(
            default=None,
            description="Updated internal notes."
        )] = None,
    ) -> str:
        """
        Update fields on an existing client record in PayTraq.

        Use this tool when a customer's address, contact info, or VAT number has changed.
        Only the fields you provide will be updated — omitted fields are left unchanged.
        """
        try:
            if email and not _EMAIL_RE.match(email):
                return f"Error: Invalid email address '{email}'."
            if country:
                err = _validate_country(country)
                if err:
                    return f"Error: {err}"
                country = country.upper()

            data: dict = {}
            if name:        data["Name"] = name
            if email:       data["Email"] = email
            if phone:       data["Phone"] = phone
            if reg_number:  data["RegNumber"] = reg_number
            if vat_number:  data["VatNumber"] = vat_number
            if country:     data["Country"] = country
            if address:     data["Address"] = address
            if city:        data["City"] = city
            if zip_code:    data["Zip"] = zip_code
            if comment:     data["Comment"] = comment
            if not data:
                return "Error: Provide at least one field to update."
            return format_response(post(f"client/{client_id}", data, "Client"))
        except Exception as e:
            raise

    @mcp.tool()
    def get_client_outstanding(
        client_id: Annotated[int, Field(
            description="Client ID to check outstanding balance for.",
            gt=0,
        )],
    ) -> str:
        """
        Get a client's outstanding balance — all unpaid invoices and total amount owed.

        Use this tool when you need to know:
        - How much a customer owes in total
        - Which specific invoices are unpaid
        - Whether it's safe to extend more credit to a customer
        """
        try:
            return format_response(get(f"client/outstanding/{client_id}"))
        except Exception as e:
            raise

    @mcp.tool()
    def list_client_contacts(
        client_id: Annotated[int, Field(
            description="Client ID whose contacts to list.",
            gt=0,
        )],
    ) -> str:
        """
        List all contact persons associated with a client.

        Use this tool when you need to find the right contact person at a company
        for sending invoices or making calls.
        """
        try:
            return format_response(get(f"client/contacts/{client_id}"))
        except Exception as e:
            raise

    @mcp.tool()
    def add_client_contact(
        client_id: Annotated[int, Field(
            description="Client ID to add a contact to.",
            gt=0,
        )],
        name: Annotated[str, Field(description="Full name of the contact person.")],
        email: Annotated[Optional[str], Field(
            default=None,
            description="Contact person's email address."
        )] = None,
        phone: Annotated[Optional[str], Field(
            default=None,
            description="Contact person's phone number."
        )] = None,
        position: Annotated[Optional[str], Field(
            default=None,
            description="Job title or position of the contact (e.g. 'CFO', 'Accountant')."
        )] = None,
    ) -> str:
        """
        Add a new contact person to an existing client record.

        Use this tool when a company has multiple contacts and you need to
        record a new person (e.g. new accountant, new purchasing manager).
        """
        try:
            if email and not _EMAIL_RE.match(email):
                return f"Error: Invalid email address '{email}'."
            data: dict = {"Name": name}
            if email:    data["Email"] = email
            if phone:    data["Phone"] = phone
            if position: data["Position"] = position
            return format_response(post(f"client/contact/{client_id}", data, "Contact"))
        except Exception as e:
            raise

    @mcp.tool()
    def list_client_banks(
        client_id: Annotated[int, Field(
            description="Client ID whose bank accounts to list.",
            gt=0,
        )],
    ) -> str:
        """
        Get bank account details for a client (IBAN, BIC/SWIFT, bank name).

        Use this tool when you need to verify or retrieve a client's bank details
        before initiating a payment or refund.
        """
        try:
            return format_response(get(f"client/banks/{client_id}"))
        except Exception as e:
            raise

    @mcp.tool()
    def list_client_groups() -> str:
        """
        List all client groups (categories) defined in PayTraq.

        Use this tool when you need group IDs for filtering or when setting up
        a new client that belongs to an existing group.
        """
        try:
            return format_response(get("clientGroups"))
        except Exception as e:
            raise

    # ── SUPPLIERS ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_suppliers(
        query: Annotated[Optional[str], Field(
            default=None,
            description="Filter by supplier name or email."
        )] = None,
        page: Annotated[int, Field(
            default=0,
            ge=0,
            description="Page number (100 records per page, starting at 0)."
        )] = 0,
    ) -> str:
        """
        List all suppliers (vendors) in PayTraq.

        Use this tool when you need to find a supplier ID before creating a
        purchase order or recording a vendor invoice.
        """
        try:
            params = {"page": page}
            if query:
                params["query"] = query
            return format_response(get("suppliers", params))
        except Exception as e:
            raise

    @mcp.tool()
    def get_supplier(
        supplier_id: Annotated[int, Field(
            description="Numeric PayTraq supplier ID.",
            gt=0,
        )],
    ) -> str:
        """
        Get full details of a supplier record by ID.

        Use this tool to retrieve a supplier's registration, VAT, address, and
        bank details before creating purchase documents.
        """
        try:
            return format_response(get(f"supplier/{supplier_id}"))
        except Exception as e:
            raise

    @mcp.tool()
    def create_supplier(
        name: Annotated[str, Field(description="Supplier company name.")],
        email: Annotated[Optional[str], Field(
            default=None,
            description="Supplier's email address."
        )] = None,
        phone: Annotated[Optional[str], Field(
            default=None,
            description="Supplier's phone number."
        )] = None,
        reg_number: Annotated[Optional[str], Field(
            default=None,
            description="Supplier's company registration number."
        )] = None,
        vat_number: Annotated[Optional[str], Field(
            default=None,
            description="Supplier's VAT registration number."
        )] = None,
        country: Annotated[Optional[str], Field(
            default=None,
            description="2-letter ISO country code (e.g. LV, EE, LT, DE)."
        )] = None,
        address: Annotated[Optional[str], Field(
            default=None,
            description="Supplier's street address."
        )] = None,
        currency: Annotated[Optional[str], Field(
            default=None,
            description="Default purchase currency, ISO 4217 (e.g. EUR, USD)."
        )] = None,
        comment: Annotated[Optional[str], Field(
            default=None,
            description="Internal notes about this supplier."
        )] = None,
    ) -> str:
        """
        Create a new supplier (vendor) record in PayTraq.

        Use this tool before creating the first purchase order for a new vendor.
        """
        try:
            if email and not _EMAIL_RE.match(email):
                return f"Error: Invalid email address '{email}'."
            if country:
                err = _validate_country(country)
                if err:
                    return f"Error: {err}"
                country = country.upper()
            if currency:
                err = _validate_currency(currency)
                if err:
                    return f"Error: {err}"
                currency = currency.upper()

            data: dict = {"Name": name}
            if email:       data["Email"] = email
            if phone:       data["Phone"] = phone
            if reg_number:  data["RegNumber"] = reg_number
            if vat_number:  data["VatNumber"] = vat_number
            if country:     data["Country"] = country
            if address:     data["Address"] = address
            if currency:    data["Currency"] = currency
            if comment:     data["Comment"] = comment
            return format_response(post("supplier", data, "Supplier"))
        except Exception as e:
            raise

    @mcp.tool()
    def update_supplier(
        supplier_id: Annotated[int, Field(
            description="ID of the supplier to update.",
            gt=0,
        )],
        name: Annotated[Optional[str], Field(
            default=None,
            description="New supplier name."
        )] = None,
        email: Annotated[Optional[str], Field(
            default=None,
            description="New email address."
        )] = None,
        phone: Annotated[Optional[str], Field(
            default=None,
            description="New phone number."
        )] = None,
        reg_number: Annotated[Optional[str], Field(
            default=None,
            description="Updated registration number."
        )] = None,
        vat_number: Annotated[Optional[str], Field(
            default=None,
            description="Updated VAT number."
        )] = None,
        country: Annotated[Optional[str], Field(
            default=None,
            description="2-letter ISO country code."
        )] = None,
        address: Annotated[Optional[str], Field(
            default=None,
            description="Updated address."
        )] = None,
        comment: Annotated[Optional[str], Field(
            default=None,
            description="Updated internal notes."
        )] = None,
    ) -> str:
        """
        Update fields on an existing supplier record.

        Use this tool when a supplier changes their address, VAT number, or
        contact information. Only provided fields are updated.
        """
        try:
            if email and not _EMAIL_RE.match(email):
                return f"Error: Invalid email address '{email}'."
            if country:
                err = _validate_country(country)
                if err:
                    return f"Error: {err}"
                country = country.upper()

            data: dict = {}
            if name:        data["Name"] = name
            if email:       data["Email"] = email
            if phone:       data["Phone"] = phone
            if reg_number:  data["RegNumber"] = reg_number
            if vat_number:  data["VatNumber"] = vat_number
            if country:     data["Country"] = country
            if address:     data["Address"] = address
            if comment:     data["Comment"] = comment
            if not data:
                return "Error: Provide at least one field to update."
            return format_response(post(f"supplier/{supplier_id}", data, "Supplier"))
        except Exception as e:
            raise

    @mcp.tool()
    def list_supplier_groups() -> str:
        """
        List all supplier groups (categories) defined in PayTraq.

        Use this tool to get group IDs when filtering suppliers or when assigning
        a new supplier to a group.
        """
        try:
            return format_response(get("supplierGroups"))
        except Exception as e:
            raise

    # ── EMPLOYEES ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_employees(
        query: Annotated[Optional[str], Field(
            default=None,
            description="Filter by employee name."
        )] = None,
        page: Annotated[int, Field(
            default=0,
            ge=0,
            description="Page number (100 records per page, starting at 0)."
        )] = 0,
    ) -> str:
        """
        List all employees in PayTraq.

        Use this tool to find employee IDs when assigning employees to documents
        or checking the employee directory.
        """
        try:
            params = {"page": page}
            if query:
                params["query"] = query
            return format_response(get("employees", params))
        except Exception as e:
            raise

    @mcp.tool()
    def get_employee(
        employee_id: Annotated[int, Field(
            description="Numeric PayTraq employee ID.",
            gt=0,
        )],
    ) -> str:
        """
        Get full details of an employee record by ID.

        Use this tool to retrieve an employee's contact info, position,
        and other details.
        """
        try:
            return format_response(get(f"employee/{employee_id}"))
        except Exception as e:
            raise

    @mcp.tool()
    def create_employee(
        name: Annotated[str, Field(description="Employee's full name.")],
        email: Annotated[Optional[str], Field(
            default=None,
            description="Employee's work email address."
        )] = None,
        phone: Annotated[Optional[str], Field(
            default=None,
            description="Employee's phone number."
        )] = None,
        position: Annotated[Optional[str], Field(
            default=None,
            description="Job title or position (e.g. 'Accountant', 'Sales Manager')."
        )] = None,
        comment: Annotated[Optional[str], Field(
            default=None,
            description="Internal notes about the employee."
        )] = None,
    ) -> str:
        """
        Create a new employee record in PayTraq.

        Use this tool when hiring a new employee who needs to be tracked in
        the accounting system.
        """
        try:
            if email and not _EMAIL_RE.match(email):
                return f"Error: Invalid email address '{email}'."
            data: dict = {"Name": name}
            if email:    data["Email"] = email
            if phone:    data["Phone"] = phone
            if position: data["Position"] = position
            if comment:  data["Comment"] = comment
            return format_response(post("employee", data, "Employee"))
        except Exception as e:
            raise

    @mcp.tool()
    def list_employee_groups() -> str:
        """
        List all employee groups (departments/categories) in PayTraq.

        Use this tool to get group IDs when organizing employees into
        departments or teams.
        """
        try:
            return format_response(get("employeeGroups"))
        except Exception as e:
            raise
