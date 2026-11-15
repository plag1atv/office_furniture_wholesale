from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MONEY_PRECISION = Decimal("0.01")


def parse_price(value):
    """Проверяет цену и преобразует её в Decimal."""
    if not isinstance(value, (str, Decimal)):
        raise ValueError("Цена должна передаваться строкой или Decimal.")

    try:
        price = Decimal(value)
    except InvalidOperation:
        raise ValueError("Цена должна быть корректным числом.") from None

    if not price.is_finite():
        raise ValueError("Цена должна быть конечным числом.")

    if price < 0:
        raise ValueError("Цена не может быть отрицательной.")

    if price > Decimal("999999999999.99"):
        raise ValueError("Цена превышает допустимое значение.")

    rounded_price = price.quantize(
        MONEY_PRECISION,
        rounding=ROUND_HALF_UP,
    )

    if price != rounded_price:
        raise ValueError("Цена должна содержать не более двух знаков после запятой.")

    return rounded_price


def validate_quantity(quantity):
    """Проверяет количество изделий."""
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise ValueError("Количество должно быть целым числом.")

    if quantity <= 0:
        raise ValueError("Количество должно быть больше нуля.")

    return quantity


def create_order_item(sku, name, quantity, unit_price):
    """Создаёт проверенную строку заказа."""
    if not isinstance(sku, str) or not sku.strip():
        raise ValueError("Необходимо указать артикул товара.")

    if not isinstance(name, str) or not name.strip():
        raise ValueError("Необходимо указать название товара.")

    return {
        "sku": sku.strip().upper(),
        "name": name.strip(),
        "quantity": validate_quantity(quantity),
        "unit_price": parse_price(unit_price),
    }


def calculate_item_total(item):
    """Рассчитывает стоимость одной строки заказа."""
    quantity = validate_quantity(item["quantity"])
    unit_price = parse_price(item["unit_price"])

    return (unit_price * quantity).quantize(
        MONEY_PRECISION,
        rounding=ROUND_HALF_UP,
    )


def calculate_order_total(items):
    """Рассчитывает общую стоимость непустого заказа."""
    if not items:
        raise ValueError("Заказ должен содержать хотя бы один товар.")

    total = Decimal("0.00")

    for item in items:
        total += calculate_item_total(item)

    return total


def format_money(value):
    """Форматирует денежную сумму для вывода."""
    formatted = f"{value:,.2f}"
    formatted = formatted.replace(",", " ").replace(".", ",")

    return f"{formatted} руб."