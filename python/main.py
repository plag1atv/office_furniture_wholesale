from inventory import print_stock
from copy import deepcopy
from order_calculations import create_order_item, format_money
from order_workflow import (
    confirm_order,
    create_order,
    get_paid_amount,
    get_remaining_amount,
    mark_ready_for_shipment,
    register_payment,
    ship_order,
    start_picking,
)


def create_demo_stock():
    """Возвращает учебные складские остатки."""
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


def create_demo_items():
    """Возвращает строки учебного заказа."""
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


def print_order_status(order):
    """Выводит состояние заказа и расчётов."""
    print("-" * 66)
    print(f"Заказ: {order['number']}")
    print(f"Покупатель: {order['customer']}")
    print(f"Статус: {order['status']}")
    print(f"Стоимость: {format_money(order['total'])}")
    print(f"Оплачено: {format_money(get_paid_amount(order))}")
    print(f"Осталось оплатить: {format_money(get_remaining_amount(order))}")


def main():
    print("=" * 66)
    print("ОБРАБОТКА ЗАКАЗА И КОНТРОЛЬ ОПЛАТЫ")
    print("=" * 66)

    stock = create_demo_stock()

    order = create_order(
        number="ORD-001",
        customer='ООО «Учебный офис»',
        items=create_demo_items(),
    )

    print("\n1. СОЗДАНИЕ ЗАКАЗА")
    print_order_status(order)

    order, stock = confirm_order(order, stock)

    print("\n2. ПОДТВЕРЖДЕНИЕ И РЕЗЕРВИРОВАНИЕ")
    print_order_status(order)

    order = register_payment(order, "35000.00", "PAY-001")

    print("\n3. ЧАСТИЧНАЯ ОПЛАТА")
    print_order_status(order)

    print("\n4. ПРОВЕРКА ЗАПРЕТА КОМПЛЕКТОВАНИЯ")

    try:
        start_picking(order)
    except ValueError as error:
        print(f"Операция отклонена: {error}")
    else:
        raise RuntimeError(
            "Ошибка: неоплаченный заказ передан на комплектование."
        )

    print("\n5. ПРОВЕРКА ПОВТОРНОГО ПЛАТЕЖА")

    try:
        register_payment(order, "35000.00", "PAY-001")
    except ValueError as error:
        print(f"Операция отклонена: {error}")
    else:
        raise RuntimeError("Ошибка: повторный платёж принят.")

    order = register_payment(order, "37500.00", "PAY-002")

    print("\n6. ПОЛНАЯ ОПЛАТА")
    print_order_status(order)

    order = start_picking(order)

    print("\n7. ПЕРЕДАЧА НА КОМПЛЕКТОВАНИЕ")
    print_order_status(order)

    print("\n8. ПРОВЕРКА КОМПЛЕКТНОСТИ")

    # Учебное подтверждение фактически подобранного количества.
    picked_quantities = {
        "ST-01": 3,
        "KR-01": 4,
    }

    order = mark_ready_for_shipment(order, picked_quantities)

    print(f"Статус: {order['status']}")

    stock_before_shipment = deepcopy(stock)

    order, stock = ship_order(
        order,
        stock,
        operation_key="SHIP-ORD-001",
    )

    print("\n9. ПРОВЕРКА ПОВТОРНОЙ ОТПРАВКИ ЗАПРОСА")

    order_after_shipment = deepcopy(order)
    stock_after_shipment = deepcopy(stock)

    repeated_order, repeated_stock = ship_order(
        order,
        stock,
        operation_key="SHIP-ORD-001",
    )

    if (
            repeated_order != order_after_shipment
            or repeated_stock != stock_after_shipment
    ):
        raise RuntimeError(
            "Повторный запрос изменил результат отгрузки."
        )

    print("Повтор с тем же ключом: новое списание не выполнено.")

    try:
        ship_order(order, stock, operation_key="SHIP-ORD-001-RETRY")
    except ValueError as error:
        print(f"Отгрузка с другим ключом отклонена: {error}")
    else:
        raise RuntimeError("Повторная отгрузка ошибочно разрешена.")

    print("\nИСТОРИЯ ЗАКАЗА")

    for event in order["history"]:
        print(f"{event['action']} → {event['status']}")

    print("\n" + "=" * 66)
    print("КОНТРОЛЬНЫЙ РЕЗУЛЬТАТ")
    print("=" * 66)

    print_order_status(order)

    print_stock(
        stock_before_shipment,
        "СКЛАД ПЕРЕД ОТГРУЗКОЙ",
    )

    print_stock(
        stock,
        "СКЛАД ПОСЛЕ ОТГРУЗКИ",
    )

    print("Повторный запрос не изменяет остатки.")
    print("Отгрузка завершена.")


if __name__ == "__main__":
    main()