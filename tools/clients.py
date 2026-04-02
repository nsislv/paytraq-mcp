"""
PayTraq MCP — Clients & Suppliers Tools
-----------------------------------------
Инструменты для работы с клиентами, поставщиками и сотрудниками.
"""

from typing import Optional
from mcp.server.fastmcp import FastMCP
from paytraq_client import get, post, format_response


def register(mcp: FastMCP) -> None:

    # ── CLIENTS ───────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_clients(
        query: Optional[str] = None,
        page: int = 0,
    ) -> str:
        """
        Получить список клиентов PayTraq.

        Args:
            query: Фильтр по имени или email (необязательно)
            page:  Страница результатов (100 записей на страницу, по умолчанию 0)
        """
        params = {"page": page}
        if query:
            params["query"] = query
        return format_response(get("clients", params))

    @mcp.tool()
    def get_client(client_id: int) -> str:
        """
        Получить детальную информацию о клиенте по ID.

        Args:
            client_id: Числовой ID клиента в PayTraq
        """
        return format_response(get(f"client/{client_id}"))

    @mcp.tool()
    def create_client(
        name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        reg_number: Optional[str] = None,
        vat_number: Optional[str] = None,
        country: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        zip_code: Optional[str] = None,
        client_type: int = 2,
        currency: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> str:
        """
        Создать нового клиента.

        Args:
            name:        Название/имя клиента (обязательно)
            email:       Email-адрес
            phone:       Телефон
            reg_number:  Регистрационный номер компании
            vat_number:  НДС номер
            country:     Двухбуквенный код страны (например, LV, EE, LT)
            address:     Адрес
            city:        Город
            zip_code:    Почтовый индекс
            client_type: Тип: 1=Физическое лицо, 2=Юридическое лицо (по умолчанию 2)
            currency:    Валюта (EUR, USD и т.д.)
            comment:     Комментарий
        """
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

    @mcp.tool()
    def update_client(
        client_id: int,
        name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        reg_number: Optional[str] = None,
        vat_number: Optional[str] = None,
        country: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        zip_code: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> str:
        """
        Обновить данные существующего клиента.

        Args:
            client_id:  ID клиента (обязательно)
            name:       Новое название/имя
            email:      Новый email
            phone:      Новый телефон
            reg_number: Регистрационный номер
            vat_number: НДС номер
            country:    Код страны
            address:    Адрес
            city:       Город
            zip_code:   Почтовый индекс
            comment:    Комментарий
        """
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
            return "❌ Error: Provide at least one field to update."
        return format_response(post(f"client/{client_id}", data, "Client"))

    @mcp.tool()
    def get_client_outstanding(client_id: int) -> str:
        """
        Получить задолженность клиента (неоплаченные счета и баланс).

        Args:
            client_id: ID клиента
        """
        return format_response(get(f"client/outstanding/{client_id}"))

    @mcp.tool()
    def list_client_contacts(client_id: int) -> str:
        """
        Получить список контактов клиента.

        Args:
            client_id: ID клиента
        """
        return format_response(get(f"client/contacts/{client_id}"))

    @mcp.tool()
    def add_client_contact(
        client_id: int,
        name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        position: Optional[str] = None,
    ) -> str:
        """
        Добавить контактное лицо к клиенту.

        Args:
            client_id: ID клиента
            name:      Имя контакта (обязательно)
            email:     Email контакта
            phone:     Телефон контакта
            position:  Должность
        """
        data: dict = {"Name": name}
        if email:    data["Email"] = email
        if phone:    data["Phone"] = phone
        if position: data["Position"] = position
        return format_response(post(f"client/contact/{client_id}", data, "Contact"))

    @mcp.tool()
    def list_client_banks(client_id: int) -> str:
        """
        Получить банковские реквизиты клиента.

        Args:
            client_id: ID клиента
        """
        return format_response(get(f"client/banks/{client_id}"))

    @mcp.tool()
    def list_client_groups() -> str:
        """Получить список групп клиентов."""
        return format_response(get("clientGroups"))

    # ── SUPPLIERS ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_suppliers(
        query: Optional[str] = None,
        page: int = 0,
    ) -> str:
        """
        Получить список поставщиков.

        Args:
            query: Фильтр по имени или email
            page:  Страница (по умолчанию 0)
        """
        params = {"page": page}
        if query:
            params["query"] = query
        return format_response(get("suppliers", params))

    @mcp.tool()
    def get_supplier(supplier_id: int) -> str:
        """
        Получить данные поставщика по ID.

        Args:
            supplier_id: ID поставщика
        """
        return format_response(get(f"supplier/{supplier_id}"))

    @mcp.tool()
    def create_supplier(
        name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        reg_number: Optional[str] = None,
        vat_number: Optional[str] = None,
        country: Optional[str] = None,
        address: Optional[str] = None,
        currency: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> str:
        """
        Создать нового поставщика.

        Args:
            name:       Название поставщика (обязательно)
            email:      Email
            phone:      Телефон
            reg_number: Регистрационный номер
            vat_number: НДС номер
            country:    Код страны (LV, EE, LT...)
            address:    Адрес
            currency:   Валюта
            comment:    Комментарий
        """
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

    @mcp.tool()
    def update_supplier(
        supplier_id: int,
        name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        reg_number: Optional[str] = None,
        vat_number: Optional[str] = None,
        country: Optional[str] = None,
        address: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> str:
        """
        Обновить данные поставщика.

        Args:
            supplier_id: ID поставщика (обязательно)
            name:        Новое название
            email:       Новый email
            phone:       Телефон
            reg_number:  Рег. номер
            vat_number:  НДС номер
            country:     Код страны
            address:     Адрес
            comment:     Комментарий
        """
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
            return "❌ Error: Provide at least one field to update."
        return format_response(post(f"supplier/{supplier_id}", data, "Supplier"))

    @mcp.tool()
    def list_supplier_groups() -> str:
        """Получить список групп поставщиков."""
        return format_response(get("supplierGroups"))

    # ── EMPLOYEES ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_employees(
        query: Optional[str] = None,
        page: int = 0,
    ) -> str:
        """
        Получить список сотрудников.

        Args:
            query: Фильтр по имени
            page:  Страница (по умолчанию 0)
        """
        params = {"page": page}
        if query:
            params["query"] = query
        return format_response(get("employees", params))

    @mcp.tool()
    def get_employee(employee_id: int) -> str:
        """
        Получить данные сотрудника по ID.

        Args:
            employee_id: ID сотрудника
        """
        return format_response(get(f"employee/{employee_id}"))

    @mcp.tool()
    def create_employee(
        name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        position: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> str:
        """
        Создать нового сотрудника.

        Args:
            name:     Имя сотрудника (обязательно)
            email:    Email
            phone:    Телефон
            position: Должность
            comment:  Комментарий
        """
        data: dict = {"Name": name}
        if email:    data["Email"] = email
        if phone:    data["Phone"] = phone
        if position: data["Position"] = position
        if comment:  data["Comment"] = comment
        return format_response(post("employee", data, "Employee"))

    @mcp.tool()
    def list_employee_groups() -> str:
        """Получить список групп сотрудников."""
        return format_response(get("employeeGroups"))
