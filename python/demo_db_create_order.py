import sys
from getpass import getpass

import psycopg

from db_orders import create_draft_order
from order_calculations import (
    calculate_item_total,
    format_money,
)


def main():
    print("=" * 76)
    print("СОЗДАНИЕ ЗАКАЗА В POSTGRESQL")
    print("=" * 76)

    login = input("Логин менеджера: ").strip()
    password = getpass("Пароль менеджера: ")

    order = create_draft_order(
        number="DB-ORD-001",
        customer_inn="0000000001",
        warehouse_name="Основной",
        items=[
            {"sku": "ST-01", "quantity": 3},
            {"sku": "KR-01", "quantity": 4},
        ],
        login=login,
        password=password,
    )

    print("\nЗАКАЗ СОХРАНЁН")
    print(f"Идентификатор: {order['id']}")
    print(f"Номер: {order['number']}")
    print(f"Покупатель: {order['customer']}")
    print(f"Склад: {order['warehouse']}")
    print(f"Менеджер: {order['manager']}")
    print(f"Статус в базе: {order['status']} — Черновик")

    print("\nСТРОКИ ЗАКАЗА")

    for item in order["items"]:
        print(
            f"{item['sku']} | {item['name']} | "
            f"{item['quantity']} шт. | "
            f"{format_money(calculate_item_total(item))}"
        )

    print(f"\nИТОГО: {format_money(order['total'])}")
    print("Заголовок, строки и история сохранены одной транзакцией.")


if __name__ == "__main__":
    try:
        main()
    except (PermissionError, ValueError, psycopg.Error, EOFError) as error:
        print(f"\nОшибка: {error}")
        sys.exit(1)