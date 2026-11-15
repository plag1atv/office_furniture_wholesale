import sys
from getpass import getpass

import psycopg

from db_orders import reserve_order_in_database


def main():
    print("=" * 76)
    print("РЕЗЕРВИРОВАНИЕ ЗАКАЗА В POSTGRESQL")
    print("=" * 76)

    login = input("Логин менеджера: ").strip()
    password = getpass("Пароль менеджера: ")

    result = reserve_order_in_database(
        number="DB-ORD-001",
        operation_key="RESERVE-DB-ORD-001",
        login=login,
        password=password,
    )

    print(f"\nЗаказ: {result['number']}")
    print(f"Статус: {result['status']} — Ожидает оплаты")

    if result["already_reserved"]:
        print("Повторный запрос: существующий резерв сохранён.")
    else:
        print("Резерв успешно создан.")

    print("\nОСТАТКИ ПОСЛЕ РЕЗЕРВИРОВАНИЯ")
    print("-" * 76)

    for row in result["balances"]:
        print(f"\nАртикул: {row['sku']}")
        print(f"Резерв этого заказа: {row['order_reserved']}")
        print(f"Физический остаток: {row['on_hand']}")
        print(f"Общий резерв: {row['reserved']}")
        print(f"Доступно: {row['available']}")

    print("\nОперация завершена.")


if __name__ == "__main__":
    try:
        main()
    except (PermissionError, ValueError, psycopg.Error, EOFError) as error:
        print(f"\nОшибка: {error}")
        sys.exit(1)