from inventory import print_stock, reserve_order
from order_calculations import (
    calculate_item_total,
    calculate_order_total,
    create_order_item,
    format_money,
)


def create_demo_stock():
    """Возвращает учебные остатки до обработки нового заказа."""
    return {
        "ST-01": {
            "on_hand": 10,
            "reserved": 2,
        },
        "KR-01": {
            "on_hand": 20,
            "reserved": 5,
        },
    }


def create_demo_order():
    """Возвращает учебный заказ из отчёта."""
    return [
        create_order_item(
            sku="ST-01",
            name="Стол офисный",
            quantity=3,
            unit_price="12500.00",
        ),
        create_order_item(
            sku="KR-01",
            name="Кресло офисное",
            quantity=4,
            unit_price="8750.00",
        ),
    ]


def print_order(items):
    """Выводит состав и стоимость заказа."""
    print("\nСОСТАВ ЗАКАЗА")
    print("-" * 66)

    for item in items:
        item_total = calculate_item_total(item)

        print(
            f"{item['sku']} | {item['name']} | "
            f"{item['quantity']} шт. × "
            f"{format_money(item['unit_price'])} = "
            f"{format_money(item_total)}"
        )

    print("-" * 66)
    print(f"ИТОГО: {format_money(calculate_order_total(items))}")


def demonstrate_failed_reservation(stock):
    """Показывает отказ без частичного изменения склада."""
    print("\nПРОВЕРКА ОТКАЗА ПРИ НЕДОСТАТКЕ ТОВАРА")

    # Кресел достаточно, но после первого заказа доступно только 5 столов.
    # Даже резерв кресел не должен сохраняться при общем отказе.
    excessive_order = [
        create_order_item(
            sku="KR-01",
            name="Кресло офисное",
            quantity=1,
            unit_price="8750.00",
        ),
        create_order_item(
            sku="ST-01",
            name="Стол офисный",
            quantity=6,
            unit_price="12500.00",
        ),
    ]

    stock_before_attempt = {
        sku: balance.copy()
        for sku, balance in stock.items()
    }

    try:
        reserve_order(excessive_order, stock)
    except ValueError as error:
        print(f"Заказ отклонён: {error}")

        if stock == stock_before_attempt:
            print("Склад не изменён. Частичный резерв не создан.")
        else:
            raise RuntimeError("Ошибка: склад изменился после отказа.")
    else:
        raise RuntimeError("Ошибка: заказ с дефицитом был принят.")


def main():
    print("=" * 66)
    print("ОПТОВАЯ ТОРГОВЛЯ ОФИСНОЙ МЕБЕЛЬЮ")
    print("Расчёт и резервирование заказа")
    print("=" * 66)

    stock = create_demo_stock()
    order_items = create_demo_order()

    print_stock(stock, "СКЛАД ДО РЕЗЕРВИРОВАНИЯ")
    print_order(order_items)

    stock = reserve_order(order_items, stock)

    print("\nЗаказ успешно зарезервирован.")
    print_stock(stock, "СКЛАД ПОСЛЕ РЕЗЕРВИРОВАНИЯ")

    demonstrate_failed_reservation(stock)


if __name__ == "__main__":
    main()