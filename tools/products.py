"""
PayTraq MCP — Products, Services & Inventory Tools
----------------------------------------------------
Инструменты для работы с:
- Товарами и услугами (CRUD, ценообразование)
- Складами и зонами загрузки
- Инвентарём и остатками
- Перевозчиками (shippers)
- Лотами/партиями товаров
"""

from typing import Optional
from mcp.server.fastmcp import FastMCP
from paytraq_client import get, post, format_response


def register(mcp: FastMCP) -> None:

    # ── PRODUCTS ──────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_products(
        query: Optional[str] = None,
        page: int = 0,
    ) -> str:
        """
        Получить список товаров.

        Args:
            query: Поиск по названию, артикулу (SKU) или штрихкоду
            page:  Страница (100 записей, по умолчанию 0)
        """
        params: dict = {"page": page}
        if query: params["query"] = query
        return format_response(get("products", params))

    @mcp.tool()
    def get_product(item_id: int) -> str:
        """
        Получить детальную информацию о товаре по ID.

        Args:
            item_id: ID товара
        """
        return format_response(get(f"product/{item_id}"))

    @mcp.tool()
    def create_product(
        name: str,
        code: Optional[str] = None,
        barcode: Optional[str] = None,
        unit: Optional[str] = None,
        product_type: int = 1,
        purchase_price: Optional[float] = None,
        sale_price: Optional[float] = None,
        tax_key: Optional[str] = None,
        description: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> str:
        """
        Создать новый товар.

        Args:
            name:           Название товара (обязательно)
            code:           Артикул/SKU
            barcode:        Штрихкод
            unit:           Единица измерения (pcs, kg, l и т.д.)
            product_type:   Тип: 1=Складируемый, 2=Расходный, 3=Основное средство
            purchase_price: Закупочная цена
            sale_price:     Цена продажи
            tax_key:        Налоговый ключ
            description:    Описание
            comment:        Комментарий
        """
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

    @mcp.tool()
    def update_product(
        item_id: int,
        name: Optional[str] = None,
        code: Optional[str] = None,
        barcode: Optional[str] = None,
        unit: Optional[str] = None,
        purchase_price: Optional[float] = None,
        sale_price: Optional[float] = None,
        tax_key: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[int] = None,
    ) -> str:
        """
        Обновить данные товара.

        Args:
            item_id:        ID товара (обязательно)
            name:           Новое название
            code:           Артикул/SKU
            barcode:        Штрихкод
            unit:           Единица измерения
            purchase_price: Закупочная цена
            sale_price:     Цена продажи
            tax_key:        Налоговый ключ
            description:    Описание
            status:         Статус: 1=Активный, 2=Снят с производства
        """
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
            return "❌ Error: Provide at least one field to update."
        return format_response(post(f"product/{item_id}", data, "Product"))

    @mcp.tool()
    def get_product_price_list(price_group_id: int) -> str:
        """
        Получить прайс-лист товаров по группе цен.

        Args:
            price_group_id: ID ценовой группы
        """
        return format_response(get(f"productPriceList/{price_group_id}"))

    @mcp.tool()
    def set_product_price(
        item_id: int,
        price: float,
        price_group_id: Optional[int] = None,
        currency: Optional[str] = None,
    ) -> str:
        """
        Установить цену товара.

        Args:
            item_id:        ID товара
            price:          Цена
            price_group_id: ID ценовой группы (если не указан — стандартная)
            currency:       Валюта (EUR, USD и т.д.)
        """
        data: dict = {"Price": price}
        if price_group_id: data["PriceGroupID"] = price_group_id
        if currency:       data["Currency"] = currency
        return format_response(post(f"productPrice/{item_id}", data, "Price"))

    @mcp.tool()
    def list_product_groups() -> str:
        """Получить список групп товаров."""
        return format_response(get("productGroups"))

    @mcp.tool()
    def list_lots(
        item_id: Optional[int] = None,
        page: int = 0,
    ) -> str:
        """
        Получить список лотов/партий товаров.

        Args:
            item_id: Фильтр по ID товара (необязательно)
            page:    Страница (по умолчанию 0)
        """
        params: dict = {"page": page}
        if item_id: params["item_id"] = item_id
        return format_response(get("lots", params))

    @mcp.tool()
    def add_product_lot(
        item_id: int,
        lot_number: str,
        expiry_date: Optional[str] = None,
        quantity: Optional[float] = None,
        comment: Optional[str] = None,
    ) -> str:
        """
        Добавить лот/партию товара.

        Args:
            item_id:     ID товара (обязательно)
            lot_number:  Номер лота/партии (обязательно)
            expiry_date: Дата истечения срока YYYY-MM-DD
            quantity:    Количество
            comment:     Комментарий
        """
        data: dict = {"LotNumber": lot_number}
        if expiry_date: data["ExpiryDate"] = expiry_date
        if quantity is not None: data["Qty"] = quantity
        if comment:     data["Comment"] = comment
        return format_response(post(f"product/lot/{item_id}", data, "Lot"))

    # ── SERVICES ──────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_services(
        query: Optional[str] = None,
        page: int = 0,
    ) -> str:
        """
        Получить список услуг.

        Args:
            query: Поиск по названию
            page:  Страница (по умолчанию 0)
        """
        params: dict = {"page": page}
        if query: params["query"] = query
        return format_response(get("services", params))

    @mcp.tool()
    def get_service(item_id: int) -> str:
        """
        Получить детальную информацию об услуге по ID.

        Args:
            item_id: ID услуги
        """
        return format_response(get(f"service/{item_id}"))

    @mcp.tool()
    def create_service(
        name: str,
        code: Optional[str] = None,
        unit: Optional[str] = None,
        sale_price: Optional[float] = None,
        tax_key: Optional[str] = None,
        description: Optional[str] = None,
    ) -> str:
        """
        Создать новую услугу.

        Args:
            name:       Название услуги (обязательно)
            code:       Код/артикул
            unit:       Единица измерения
            sale_price: Цена продажи
            tax_key:    Налоговый ключ
            description: Описание
        """
        data: dict = {"Name": name}
        if code:        data["Code"] = code
        if unit:        data["Unit"] = unit
        if sale_price is not None: data["SalePrice"] = sale_price
        if tax_key:     data["TaxKey"] = tax_key
        if description: data["Description"] = description
        return format_response(post("service", data, "Service"))

    @mcp.tool()
    def update_service(
        item_id: int,
        name: Optional[str] = None,
        code: Optional[str] = None,
        sale_price: Optional[float] = None,
        tax_key: Optional[str] = None,
        description: Optional[str] = None,
    ) -> str:
        """
        Обновить данные услуги.

        Args:
            item_id:     ID услуги (обязательно)
            name:        Новое название
            code:        Код/артикул
            sale_price:  Цена продажи
            tax_key:     Налоговый ключ
            description: Описание
        """
        data: dict = {}
        if name:        data["Name"] = name
        if code:        data["Code"] = code
        if sale_price is not None: data["SalePrice"] = sale_price
        if tax_key:     data["TaxKey"] = tax_key
        if description: data["Description"] = description
        if not data:
            return "❌ Error: Provide at least one field to update."
        return format_response(post(f"service/{item_id}", data, "Service"))

    @mcp.tool()
    def list_service_groups() -> str:
        """Получить список групп услуг."""
        return format_response(get("serviceGroups"))

    # ── WAREHOUSES & INVENTORY ────────────────────────────────────────────────

    @mcp.tool()
    def list_warehouses() -> str:
        """Получить список складов."""
        return format_response(get("warehouses"))

    @mcp.tool()
    def get_warehouse(warehouse_id: int) -> str:
        """
        Получить информацию о складе по ID.

        Args:
            warehouse_id: ID склада
        """
        return format_response(get(f"warehouse/{warehouse_id}"))

    @mcp.tool()
    def get_current_inventory(warehouse_id: int) -> str:
        """
        Получить текущие остатки на складе.

        Args:
            warehouse_id: ID склада
        """
        return format_response(get(f"currentInventory/{warehouse_id}"))

    @mcp.tool()
    def get_product_inventory(item_id: int) -> str:
        """
        Получить остатки конкретного товара по всем складам.

        Args:
            item_id: ID товара
        """
        return format_response(get(f"productInventory/{item_id}"))

    @mcp.tool()
    def list_loading_areas() -> str:
        """Получить список зон загрузки/отгрузки."""
        return format_response(get("loadingAreas"))

    @mcp.tool()
    def list_shippers(page: int = 0) -> str:
        """
        Получить список перевозчиков.

        Args:
            page: Страница (по умолчанию 0)
        """
        return format_response(get("shippers", {"page": page}))

    @mcp.tool()
    def create_shipper(
        name: str,
        contact: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
    ) -> str:
        """
        Добавить нового перевозчика.

        Args:
            name:    Название перевозчика (обязательно)
            contact: Контактное лицо
            phone:   Телефон
            email:   Email
        """
        data: dict = {"ShipperName": name}
        if contact: data["Contact"] = contact
        if phone:   data["Phone"] = phone
        if email:   data["Email"] = email
        return format_response(post("shipper", data, "Shipper"))
