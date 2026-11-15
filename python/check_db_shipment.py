import sys
from getpass import getpass
from unittest.mock import patch
from uuid import uuid4

import psycopg

from check_db_transactions import (
    ConnectionProxy,
    InjectedFailure,
    create_test_warehouse,
    read_snapshot,
)
from database import get_connection
from db_order_closing import close_order_in_database
from db_orders import (
    create_draft_order,
    register_payment_in_database,
    reserve_order_in_database,
)
from db_warehouse import (
    prepare_order_for_shipment,
    ship_order_in_database,
)


def shipment_snapshot(warehouse_id, order_id):
    """Читает остатки, заказ и все записи, связанные с отгрузкой."""
    result = read_snapshot(warehouse_id, order_id)

    queries = {
        "reservations": """
            SELECT r.*
            FROM public.reservations AS r
            WHERE r.order_id = %s
            ORDER BY r.id
        """,
        "shipments": """
            SELECT s.*
            FROM public.shipments AS s
            WHERE s.order_id = %s
            ORDER BY s.id
        """,
        "shipment_items": """
            SELECT si.*
            FROM public.shipment_items AS si
            WHERE si.order_id = %s
            ORDER BY si.id
        """,
        "movements": """
            SELECT sm.*
            FROM public.stock_movements AS sm
            JOIN public.shipment_items AS si
                ON si.id = sm.shipment_item_id
            WHERE si.order_id = %s
            ORDER BY sm.id
        """,
        "history": """
            SELECT h.*
            FROM public.order_history AS h
            WHERE h.order_id = %s
            ORDER BY h.id
        """,
    }

    with get_connection() as connection:
        with connection.cursor() as cursor:
            for name, query in queries.items():
                cursor.execute(query, (order_id,))
                result[name] = cursor.fetchall()

    return result


def main():
    print("=" * 76)
    print("ПРОВЕРКА ОТКАТА И ОДНОКРАТНОСТИ ОТГРУЗКИ")
    print("=" * 76)

    manager_password = getpass("Пароль manager: ")
    accountant_password = getpass("Пароль accountant: ")
    warehouse_password = getpass("Пароль warehouse: ")

    suffix = uuid4().hex[:8]
    warehouse_id, warehouse_name = create_test_warehouse(
        f"SHIP-{suffix}"
    )
    number = f"SHIP-TEST-{suffix}"
    operation_key = f"SHIPMENT-{suffix}"

    order = create_draft_order(
        number=number,
        customer_inn="0000000001",
        warehouse_name=warehouse_name,
        items=[
            {"sku": "ST-01", "quantity": 1},
            {"sku": "KR-01", "quantity": 1},
        ],
        login="manager",
        password=manager_password,
    )

    reserve_order_in_database(
        number,
        f"RESERVE-{suffix}",
        "manager",
        manager_password,
    )

    register_payment_in_database(
        number,
        "21250.00",
        f"PAY-SHIP-TEST-{suffix}",
        "accountant",
        accountant_password,
    )

    prepare_order_for_shipment(
        number,
        {"ST-01": 1, "KR-01": 1},
        "warehouse",
        warehouse_password,
    )

    print(f"\nТестовый заказ: {number}")
    print(f"Тестовый склад: {warehouse_name}")

    print("\n1. СБОЙ ПОСЛЕ ПЕРВОГО СПИСАНИЯ")

    before = shipment_snapshot(warehouse_id, order["id"])
    failure_state = {"injected": False}

    def fail_after_write_off(query):
        if query.startswith(
            "UPDATE PUBLIC.STOCK_BALANCES SET ON_HAND = ON_HAND -"
        ):
            failure_state["injected"] = True
            raise InjectedFailure(
                "Контрольный сбой после первого списания товара"
            )

    def connection_factory():
        return ConnectionProxy(
            get_connection(),
            after_execute=fail_after_write_off,
        )

    try:
        with patch("db_warehouse.get_connection", connection_factory):
            ship_order_in_database(
                number,
                operation_key,
                "warehouse",
                warehouse_password,
            )
    except InjectedFailure as error:
        print(f"Искусственный сбой получен: {error}")
    else:
        raise RuntimeError("Ожидаемый сбой не возник.")

    if not failure_state["injected"]:
        raise RuntimeError("Проверка не дошла до списания.")

    after_failure = shipment_snapshot(warehouse_id, order["id"])

    if after_failure != before:
        raise RuntimeError("После сбоя отгрузка откатилась не полностью.")

    print(
        "ПРОЙДЕНО: списание, отгрузка, её строки, "
        "резервы и история полностью откачены."
    )

    # После успешной проверки отката выполняем настоящую отгрузку.
    ship_order_in_database(
        number,
        operation_key,
        "warehouse",
        warehouse_password,
    )

    completed = shipment_snapshot(warehouse_id, order["id"])

    if completed["order"]["status"] != "completed":
        raise RuntimeError("Заказ не завершён.")

    if (
        len(completed["shipments"]) != 1
        or len(completed["shipment_items"]) != 2
        or len(completed["movements"]) != 2
    ):
        raise RuntimeError("Неверный состав сохранённой отгрузки.")

    print("Успешный повтор после сбоя: отгрузка сохранена.")

    print("\n2. ПОВТОР С ТЕМ ЖЕ КЛЮЧОМ")

    result = ship_order_in_database(
        number,
        operation_key,
        "warehouse",
        warehouse_password,
    )

    if not result["repeated"]:
        raise RuntimeError("Повторный запрос не распознан.")

    if shipment_snapshot(warehouse_id, order["id"]) != completed:
        raise RuntimeError("Повторный запрос изменил данные.")

    print("ПРОЙДЕНО: повтор не создал новых записей и списаний.")

    print("\n3. ПОВТОР С ДРУГИМ КЛЮЧОМ")

    try:
        ship_order_in_database(
            number,
            f"OTHER-{suffix}",
            "warehouse",
            warehouse_password,
        )
    except ValueError as error:
        print(f"Операция отклонена: {error}")
    else:
        raise RuntimeError("Вторая отгрузка ошибочно разрешена.")

    if shipment_snapshot(warehouse_id, order["id"]) != completed:
        raise RuntimeError("Отклонённая отгрузка изменила данные.")

    print("ПРОЙДЕНО: вторая отгрузка запрещена.")

    print("\n4. ОТМЕНА ПОСЛЕ ОТГРУЗКИ")

    try:
        close_order_in_database(
            number,
            "cancel",
            "Проверка запрета отмены",
            "manager",
            manager_password,
        )
    except ValueError as error:
        print(f"Операция отклонена: {error}")
    else:
        raise RuntimeError("Отмена завершённого заказа разрешена.")

    if shipment_snapshot(warehouse_id, order["id"]) != completed:
        raise RuntimeError("Попытка отмены изменила данные.")

    print("ПРОЙДЕНО: завершённый заказ не изменён.")
    print("\nИТОГ: 4 проверки отгрузки пройдены.")


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
        print(f"\nПРОВЕРКА НЕ ПРОЙДЕНА: {error}")
        sys.exit(1)