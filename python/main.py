from order_calculations import (
    calculate_item_total,
    calculate_order_total,
    create_order_item,
    format_money,
)


def print_order(items):
    """Выводит состав и стоимость заказа."""
    print("=" * 76)
    print("ОПТОВАЯ ТОРГОВЛЯ ОФИСНОЙ МЕБЕЛЬЮ")
    print("Расчёт стоимости заказа")
    print("=" * 76)

    for position, item in enumerate(items, start=1):
        item_total = calculate_item_total(item)

        print(f"\nПозиция {position}")
        print(f"Артикул: {item['sku']}")
        print(f"Наименование: {item['name']}")
        print(f"Количество: {item['quantity']} шт.")
        print(f"Цена за единицу: {format_money(item['unit_price'])}")
        print(f"Стоимость позиции: {format_money(item_total)}")

    print("\n" + "-" * 76)
    print(f"ИТОГО: {format_money(calculate_order_total(items))}")
    print("=" * 76)


def main():
    order_items = [
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

    print_order(order_items)


if __name__ == "__main__":
    main()