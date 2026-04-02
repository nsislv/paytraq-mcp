"""
PayTraq MCP — Sales & Purchase Documents Tools
------------------------------------------------
Инструменты для работы с документами:
- Продажи: счета, заказы, квитанции, кредит-ноты
- Закупки: заказы поставщикам, счета поставщиков
- Платежи
- Вложения
"""

from typing import Optional
from mcp.server.fastmcp import FastMCP
from paytraq_client import get, post, format_response


def register(mcp: FastMCP) -> None:

    # ── SALES DOCUMENTS ───────────────────────────────────────────────────────

    @mcp.tool()
    def list_sales(
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_till: Optional[str] = None,
        client_id: Optional[int] = None,
        query: Optional[str] = None,
        page: int = 0,
        reverse: bool = False,
    ) -> str:
        """
        Получить список документов продаж (счета, заказы, квитанции, кредит-ноты).

        Args:
            status:    Фильтр по статусу: draft | approved | posted | paid | voided
            date_from: Дата начала в формате YYYY-MM-DD
            date_till: Дата конца в формате YYYY-MM-DD
            client_id: Фильтр по ID клиента
            query:     Текстовый поиск по номеру документа
            page:      Страница (100 записей, по умолчанию 0)
            reverse:   True — сортировка по убыванию
        """
        params: dict = {"page": page}
        if status:    params["status"] = status
        if date_from: params["date_from"] = date_from
        if date_till: params["date_till"] = date_till
        if client_id: params["client_id"] = client_id
        if query:     params["query"] = query
        if reverse:   params["reverse"] = "true"
        return format_response(get("sales", params))

    @mcp.tool()
    def get_sale(document_id: int) -> str:
        """
        Получить детали документа продажи по ID.

        Args:
            document_id: ID документа
        """
        return format_response(get(f"sale/{document_id}"))

    @mcp.tool()
    def create_sale(
        client_id: int,
        document_date: str,
        sale_type: str = "sales_invoice",
        operation: str = "sell_goods",
        currency: str = "EUR",
        items: Optional[list] = None,
        ref_number: Optional[str] = None,
        due_date: Optional[str] = None,
        comment: Optional[str] = None,
        warehouse_id: Optional[int] = None,
    ) -> str:
        """
        Создать новый документ продажи (счёт, заказ, квитанцию и т.д.).

        Args:
            client_id:     ID клиента (обязательно)
            document_date: Дата документа в формате YYYY-MM-DD (обязательно)
            sale_type:     Тип: sales_invoice | sales_order | sales_proforma | sales_receipt | credit_note
            operation:     Операция: sell_goods | sell_services | other_income
            currency:      Валюта (EUR, USD и т.д.)
            items:         Список позиций: [{"ItemID": 1, "Qty": 2, "Price": 10.00}, ...]
            ref_number:    Номер/ссылка документа
            due_date:      Срок оплаты YYYY-MM-DD
            comment:       Комментарий/примечания
            warehouse_id:  ID склада
        """
        data: dict = {
            "ClientID": client_id,
            "DocumentDate": document_date,
            "SaleType": sale_type,
            "Operation": operation,
            "Currency": currency,
        }
        if ref_number:    data["DocumentRef"] = ref_number
        if due_date:      data["DueDate"] = due_date
        if comment:       data["Comment"] = comment
        if warehouse_id:  data["WarehouseID"] = warehouse_id

        if items:
            data["LineItems"] = {"LineItem": items}

        return format_response(post("sales", data, "Document"))

    @mcp.tool()
    def approve_sale(document_id: int) -> str:
        """
        Утвердить документ продажи (перевести из черновика в approved).

        Args:
            document_id: ID документа
        """
        return format_response(post(f"sale/{document_id}/approve", {}, "Document"))

    @mcp.tool()
    def post_sale(document_id: int) -> str:
        """
        Провести документ продажи в бухгалтерии (post to accounting).

        Args:
            document_id: ID документа
        """
        return format_response(post(f"sale/{document_id}/post", {}, "Document"))

    @mcp.tool()
    def void_sale(document_id: int) -> str:
        """
        Аннулировать документ продажи.

        Args:
            document_id: ID документа
        """
        return format_response(post(f"sale/{document_id}/void", {}, "Document"))

    @mcp.tool()
    def record_sale_payment(
        document_id: int,
        amount: float,
        payment_date: str,
        payment_method: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> str:
        """
        Зафиксировать оплату по документу продажи.

        Args:
            document_id:    ID документа
            amount:         Сумма оплаты
            payment_date:   Дата оплаты YYYY-MM-DD
            payment_method: Метод оплаты (cash, bank_transfer и т.д.)
            comment:        Комментарий
        """
        data: dict = {
            "Amount": amount,
            "PaymentDate": payment_date,
        }
        if payment_method: data["PaymentMethod"] = payment_method
        if comment:        data["Comment"] = comment
        return format_response(post(f"sale/{document_id}/payment", data, "Payment"))

    @mcp.tool()
    def send_sale(
        document_id: int,
        email: Optional[str] = None,
    ) -> str:
        """
        Отправить документ продажи клиенту по email.

        Args:
            document_id: ID документа
            email:       Email получателя (если не указан — берётся email клиента)
        """
        data: dict = {}
        if email: data["Email"] = email
        return format_response(post(f"sale/{document_id}/send", data, "Send"))

    @mcp.tool()
    def get_sale_pdf(document_id: int) -> str:
        """
        Получить ссылку/данные PDF документа продажи.

        Args:
            document_id: ID документа
        """
        return format_response(get(f"sale/{document_id}/pdf"))

    # ── PURCHASES ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_purchases(
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_till: Optional[str] = None,
        supplier_id: Optional[int] = None,
        page: int = 0,
        reverse: bool = False,
    ) -> str:
        """
        Получить список документов закупок.

        Args:
            status:      Фильтр по статусу: draft | approved | posted | paid | voided
            date_from:   Дата начала YYYY-MM-DD
            date_till:   Дата конца YYYY-MM-DD
            supplier_id: Фильтр по ID поставщика
            page:        Страница (по умолчанию 0)
            reverse:     True — по убыванию
        """
        params: dict = {"page": page}
        if status:      params["status"] = status
        if date_from:   params["date_from"] = date_from
        if date_till:   params["date_till"] = date_till
        if supplier_id: params["supplier_id"] = supplier_id
        if reverse:     params["reverse"] = "true"
        return format_response(get("purchases", params))

    @mcp.tool()
    def get_purchase(document_id: int) -> str:
        """
        Получить детали документа закупки по ID.

        Args:
            document_id: ID документа
        """
        return format_response(get(f"purchase/{document_id}"))

    @mcp.tool()
    def create_purchase(
        supplier_id: int,
        document_date: str,
        currency: str = "EUR",
        items: Optional[list] = None,
        ref_number: Optional[str] = None,
        due_date: Optional[str] = None,
        comment: Optional[str] = None,
        warehouse_id: Optional[int] = None,
    ) -> str:
        """
        Создать новый документ закупки.

        Args:
            supplier_id:   ID поставщика (обязательно)
            document_date: Дата документа YYYY-MM-DD (обязательно)
            currency:      Валюта (EUR, USD и т.д.)
            items:         Список позиций: [{"ItemID": 1, "Qty": 2, "Price": 10.00}, ...]
            ref_number:    Номер/ссылка документа поставщика
            due_date:      Срок оплаты YYYY-MM-DD
            comment:       Комментарий
            warehouse_id:  ID склада
        """
        data: dict = {
            "SupplierID": supplier_id,
            "DocumentDate": document_date,
            "Currency": currency,
        }
        if ref_number:   data["DocumentRef"] = ref_number
        if due_date:     data["DueDate"] = due_date
        if comment:      data["Comment"] = comment
        if warehouse_id: data["WarehouseID"] = warehouse_id
        if items:        data["LineItems"] = {"LineItem": items}

        return format_response(post("purchases", data, "Document"))

    @mcp.tool()
    def approve_purchase(document_id: int) -> str:
        """
        Утвердить документ закупки.

        Args:
            document_id: ID документа
        """
        return format_response(post(f"purchase/{document_id}/approve", {}, "Document"))

    @mcp.tool()
    def post_purchase(document_id: int) -> str:
        """
        Провести документ закупки в бухгалтерии.

        Args:
            document_id: ID документа
        """
        return format_response(post(f"purchase/{document_id}/post", {}, "Document"))

    @mcp.tool()
    def record_purchase_payment(
        document_id: int,
        amount: float,
        payment_date: str,
        comment: Optional[str] = None,
    ) -> str:
        """
        Зафиксировать оплату по документу закупки.

        Args:
            document_id:  ID документа
            amount:       Сумма оплаты
            payment_date: Дата оплаты YYYY-MM-DD
            comment:      Комментарий
        """
        data: dict = {"Amount": amount, "PaymentDate": payment_date}
        if comment: data["Comment"] = comment
        return format_response(post(f"purchase/{document_id}/payment", data, "Payment"))

    # ── PAYMENTS ──────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_payments(
        date_from: Optional[str] = None,
        date_till: Optional[str] = None,
        page: int = 0,
    ) -> str:
        """
        Получить список платежей.

        Args:
            date_from: Дата начала YYYY-MM-DD
            date_till: Дата конца YYYY-MM-DD
            page:      Страница (по умолчанию 0)
        """
        params: dict = {"page": page}
        if date_from: params["date_from"] = date_from
        if date_till: params["date_till"] = date_till
        return format_response(get("payments", params))

    @mcp.tool()
    def get_payment(payment_id: int) -> str:
        """
        Получить детали платежа по ID.

        Args:
            payment_id: ID платежа
        """
        return format_response(get(f"payment/{payment_id}"))

    # ── ATTACHMENTS ───────────────────────────────────────────────────────────

    @mcp.tool()
    def list_attachments(document_id: int) -> str:
        """
        Получить список вложений к документу.

        Args:
            document_id: ID документа (продажи или закупки)
        """
        return format_response(get(f"attachments/{document_id}"))
