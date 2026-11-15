from copy import deepcopy

from inventory import print_stock
from main import create_demo_items, create_demo_stock
from order_calculations import format_money
from order_workflow import (
    cancel_order,
    confirm_order,
    create_order,
    get_paid_amount,
    register_payment,
)


def main():
    print("=" * 66)
    print("ОТМЕНА ЗАКАЗА И ОСВОБОЖДЕНИЕ РЕЗЕРВА")
    print("=" * 66)

    stock = create_demo_stock()
    initial_stock = deepcopy(stock)

    order = create_order(
        number="ORD-002",
        customer='ООО «Учебный офис»',
        items=create_demo_items(),
    )

    order, stock = confirm_order(order, stock)

    print(f"\nЗаказ: {order['number']}")
    print(f"Статус после подтверждения: {order['status']}")
    print_stock(stock, "СКЛАД ПОСЛЕ РЕЗЕРВИРОВАНИЯ")

    order = register_payment(
        order,
        amount="35000.00",
        external_ref="PAY-ORD-002-001",
    )

    print(f"\nПолучена частичная оплата: {format_money(get_paid_amount(order))}")

    order, stock = cancel_order(
        order,
        stock,
        reason="Покупатель отказался от заказа",
    )

    print("\nРЕЗУЛЬТАТ ОТМЕНЫ")
    print(f"Статус: {order['status']}")
    print(f"Причина: {order['cancellation_reason']}")
    print(f"Сохранённая сумма платежей: {format_money(get_paid_amount(order))}")

    if order["refund_required"]:
        print("Требуется урегулирование расчётов с покупателем.")

    print_stock(stock, "СКЛАД ПОСЛЕ ОТМЕНЫ")

    if stock != initial_stock:
        raise RuntimeError(
            "После отмены склад не вернулся к исходному состоянию."
        )

    print("Проверка пройдена: освобождён только резерв этого заказа.")
    print("Физическое количество товара не изменилось.")

    print("\nПРОВЕРКА ПОВТОРНОЙ ОТМЕНЫ")

    order_before_retry = deepcopy(order)
    stock_before_retry = deepcopy(stock)

    try:
        cancel_order(order, stock, reason="Повторный запрос отмены")
    except ValueError as error:
        print(f"Операция отклонена: {error}")
    else:
        raise RuntimeError("Повторная отмена ошибочно разрешена.")

    if order != order_before_retry or stock != stock_before_retry:
        raise RuntimeError("Повторная отмена изменила данные.")

    print("Повторная отмена не изменила заказ и склад.")

    print("\nИСТОРИЯ ЗАКАЗА")

    for event in order["history"]:
        print(f"{event['action']} → {event['status']}")


if __name__ == "__main__":
    main()