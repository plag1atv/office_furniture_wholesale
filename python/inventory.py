from order_calculations import validate_quantity


def validate_stock_balance(balance):
    """Проверяет корректность складского остатка."""
    on_hand = balance["on_hand"]
    reserved = balance["reserved"]

    for value in (on_hand, reserved):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Складские количества должны быть целыми числами.")

        if value < 0:
            raise ValueError("Складские количества не могут быть отрицательными.")

    if reserved > on_hand:
        raise ValueError("Резерв не может превышать физический остаток.")


def get_available_quantity(balance):
    """Возвращает количество товара, доступное для нового заказа."""
    validate_stock_balance(balance)

    return balance["on_hand"] - balance["reserved"]


def aggregate_order_quantities(items):
    """Объединяет потребность по повторяющимся артикулам."""
    if not items:
        raise ValueError("Нельзя зарезервировать пустой заказ.")

    required_quantities = {}

    for item in items:
        sku = item["sku"]
        quantity = validate_quantity(item["quantity"])

        required_quantities[sku] = (
            required_quantities.get(sku, 0) + quantity
        )

    return required_quantities


def reserve_order(items, stock):
    """
    Проверяет весь заказ и возвращает новые остатки с резервом.

    Исходный словарь stock не изменяется.
    При нехватке хотя бы одного товара операция отклоняется целиком.
    """
    required_quantities = aggregate_order_quantities(items)

    # Сначала проверяем наличие всех позиций.
    for sku, required in required_quantities.items():
        if sku not in stock:
            raise ValueError(f"Товар {sku} отсутствует на складе.")

        available = get_available_quantity(stock[sku])

        if required > available:
            raise ValueError(
                f"Недостаточно товара {sku}: "
                f"требуется {required} шт., доступно {available} шт."
            )

    # Создаём независимую копию складских записей.
    updated_stock = {
        sku: balance.copy()
        for sku, balance in stock.items()
    }

    # Меняем резерв только после успешной проверки всего заказа.
    for sku, required in required_quantities.items():
        updated_stock[sku]["reserved"] += required

    return updated_stock


def print_stock(stock, title):
    """Выводит физический остаток, резерв и доступное количество."""
    print(f"\n{title}")
    print("-" * 66)
    print(
        f"{'Артикул':<12}"
        f"{'В наличии':>14}"
        f"{'В резерве':>14}"
        f"{'Доступно':>14}"
    )
    print("-" * 66)

    for sku in sorted(stock):
        balance = stock[sku]
        available = get_available_quantity(balance)

        print(
            f"{sku:<12}"
            f"{balance['on_hand']:>14}"
            f"{balance['reserved']:>14}"
            f"{available:>14}"
        )

    print("-" * 66)