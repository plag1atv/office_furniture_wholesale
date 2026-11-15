import sys
from getpass import getpass

import psycopg

from db_warehouse import (
    prepare_order_for_shipment,
    ship_order_in_database,
)


def print_balances(title, rows):
    print(f"\n{title}")
    print("-" * 66)
    print(
        f"{'Артикул':<12}"
        f"{'В наличии':>14}"
        f"{'В резерве':>14}"
        f"{'Доступно':>14}"
    )

    for row in sorted(rows, key=lambda record: record["sku"]):
        print(
            f"{row['sku']:<12}"
            f"{row['on_hand']:>14}"
            f"{row['reserved']:>14}"
            f"{row['available']:>14}"
        )


def main():
    print("=" * 66)
    print("КОМПЛЕКТОВАНИЕ И ОТГРУЗКА В POSTGRESQL")
    print("=" * 66)

    login = input("Логин кладовщика: ").strip()
    password = getpass("Пароль кладовщика: ")

    status = prepare_order_for_shipment(
        number="DB-ORD-001",
        picked_quantities={"ST-01": 3, "KR-01": 4},
        login=login,
        password=password,
    )

    print(f"\nСтатус после подготовки: {status}")

    result = ship_order_in_database(
        number="DB-ORD-001",
        operation_key="SHIP-DB-ORD-001",
        login=login,
        password=password,
    )

    print(f"Заказ: {result['number']}")
    print(f"Идентификатор отгрузки: {result['shipment_id']}")

    if result["repeated"]:
        print("Повторный запрос: новое списание не выполнено.")
    else:
        print("Отгрузка сохранена. Статус заказа: completed.")
        print_balances("ДО ОТГРУЗКИ", result["before"])

    print_balances("ТЕКУЩИЕ ОСТАТКИ", result["after"])

    repeated_result = ship_order_in_database(
        number="DB-ORD-001",
        operation_key="SHIP-DB-ORD-001",
        login=login,
        password=password,
    )

    if (
        not repeated_result["repeated"]
        or repeated_result["shipment_id"] != result["shipment_id"]
        or repeated_result["after"] != result["after"]
    ):
        raise RuntimeError("Нарушена защита от повторной отгрузки.")

    print("\nПроверка повтора пройдена: отгрузка одна, остатки не изменились.")


if __name__ == "__main__":
    try:
        main()
    except (
        PermissionError,
        ValueError,
        RuntimeError,
        psycopg.Error,
        EOFError,
    ) as error:
        print(f"\nОшибка: {error}")
        sys.exit(1)