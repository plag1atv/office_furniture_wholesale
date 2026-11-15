import sys
from concurrent.futures import ThreadPoolExecutor
from getpass import getpass
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import psycopg

from database import get_connection
from db_order_closing import close_order_in_database
from db_orders import (
    create_draft_order,
    reserve_order_in_database,
)


class InjectedFailure(RuntimeError):
    """Искусственный сбой для проверки отката."""


class CursorProxy:
    """Выполняет настоящие SQL-запросы с тестовыми обработчиками."""

    def __init__(self, cursor, before_execute=None, after_execute=None):
        self.cursor = cursor
        self.before_execute = before_execute
        self.after_execute = after_execute

    def __enter__(self):
        self.cursor.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self.cursor.__exit__(exc_type, exc_value, traceback)

    def __getattr__(self, name):
        return getattr(self.cursor, name)

    def execute(self, query, params=None):
        normalized_query = " ".join(str(query).upper().split())

        if self.before_execute is not None:
            self.before_execute(normalized_query)

        result = self.cursor.execute(query, params)

        if self.after_execute is not None:
            self.after_execute(normalized_query)

        return result


class ConnectionProxy:
    """Сохраняет реальное поведение COMMIT и ROLLBACK."""

    def __init__(self, connection, before_execute=None, after_execute=None):
        self.connection = connection
        self.before_execute = before_execute
        self.after_execute = after_execute

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self.connection.__exit__(
            exc_type, exc_value, traceback
        )

    def cursor(self):
        return CursorProxy(
            self.connection.cursor(),
            self.before_execute,
            self.after_execute,
        )


def create_test_warehouse(suffix):
    name = f"Проверка транзакций {suffix}"

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.warehouses (name, address)
                VALUES (%s, %s)
                RETURNING id
                """,
                (name, "Изолированный учебный склад"),
            )
            warehouse_id = cursor.fetchone()["id"]

            cursor.execute(
                """
                SELECT id, sku
                FROM public.products
                WHERE sku IN ('ST-01', 'KR-01')
                """
            )
            products = cursor.fetchall()

            if len(products) != 2:
                raise ValueError("Не найдены учебные товары.")

            for product in products:
                quantity = 8 if product["sku"] == "ST-01" else 20

                cursor.execute(
                    """
                    INSERT INTO public.stock_balances (
                        warehouse_id, product_id, on_hand, reserved
                    )
                    VALUES (%s, %s, %s, 0)
                    """,
                    (warehouse_id, product["id"], quantity),
                )

    return warehouse_id, name


def read_snapshot(warehouse_id, order_id):
    """Читает фактическое состояние через отдельное соединение."""
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT product_id, on_hand, reserved
                FROM public.stock_balances
                WHERE warehouse_id = %s
                ORDER BY product_id
                """,
                (warehouse_id,),
            )
            balances = cursor.fetchall()

            cursor.execute(
                """
                SELECT status, reserve_key
                FROM public.orders
                WHERE id = %s
                """,
                (order_id,),
            )
            order = cursor.fetchone()

            cursor.execute(
                """
                SELECT count(*) AS quantity
                FROM public.reservations
                WHERE order_id = %s
                """,
                (order_id,),
            )
            reservation_count = cursor.fetchone()["quantity"]

            cursor.execute(
                """
                SELECT count(*) AS quantity
                FROM public.order_history
                WHERE order_id = %s
                """,
                (order_id,),
            )
            history_count = cursor.fetchone()["quantity"]

    return {
        "balances": balances,
        "order": order,
        "reservation_count": reservation_count,
        "history_count": history_count,
    }


def create_test_order(number, warehouse_name, items, login, password):
    return create_draft_order(
        number=number,
        customer_inn="0000000001",
        warehouse_name=warehouse_name,
        items=items,
        login=login,
        password=password,
    )


def check_concurrent_reservation(
    suffix, warehouse_id, warehouse_name, login, password
):
    numbers = [f"CONCURRENT-A-{suffix}", f"CONCURRENT-B-{suffix}"]

    for number in numbers:
        create_test_order(
            number,
            warehouse_name,
            [{"sku": "ST-01", "quantity": 6}],
            login,
            password,
        )

    # Обе реальные транзакции доходят до запроса блокировки остатка.
    barrier = Barrier(2)

    def synchronize_stock_query(query):
        if query.startswith(
            "SELECT ON_HAND, RESERVED FROM PUBLIC.STOCK_BALANCES"
        ):
            barrier.wait(timeout=20)

    def connection_factory():
        return ConnectionProxy(
            get_connection(),
            before_execute=synchronize_stock_query,
        )

    def reserve(number):
        try:
            reserve_order_in_database(
                number,
                f"RESERVE-{number}",
                login,
                password,
            )
            return number, True, "Резерв создан"
        except ValueError as error:
            return number, False, str(error)

    with patch("db_orders.get_connection", connection_factory):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(reserve, numbers))

    for number, success, message in results:
        print(f"{number}: {message}")

    if sum(success for number, success, message in results) != 1:
        raise RuntimeError("Ожидалось ровно одно успешное резервирование.")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT sb.on_hand, sb.reserved
                FROM public.stock_balances AS sb
                JOIN public.products AS p ON p.id = sb.product_id
                WHERE sb.warehouse_id = %s AND p.sku = 'ST-01'
                """,
                (warehouse_id,),
            )
            balance = cursor.fetchone()

    if balance != {"on_hand": 8, "reserved": 6}:
        raise RuntimeError(f"Неверный итог конкуренции: {balance}")

    print("ПРОЙДЕНО: из 8 столов зарезервировано 6, доступно 2.")

    # Освобождаем резерв победившего заказа.
    # Второй заказ отменяется как черновик.
    for number in numbers:
        close_order_in_database(
            number,
            "cancel",
            "Завершение проверки параллельного резервирования",
            login,
            password,
        )


def check_reservation_rollback(
    suffix, warehouse_id, warehouse_name, login, password
):
    number = f"ROLLBACK-{suffix}"

    order = create_test_order(
        number,
        warehouse_name,
        [
            {"sku": "ST-01", "quantity": 1},
            {"sku": "KR-01", "quantity": 1},
        ],
        login,
        password,
    )

    before = read_snapshot(warehouse_id, order["id"])
    failure_state = {"injected": False}

    def fail_after_stock_update(query):
        if query.startswith(
            "UPDATE PUBLIC.STOCK_BALANCES SET RESERVED = RESERVED +"
        ):
            failure_state["injected"] = True
            raise InjectedFailure(
                "Контрольный сбой после первого изменения остатка"
            )

    def connection_factory():
        return ConnectionProxy(
            get_connection(),
            after_execute=fail_after_stock_update,
        )

    try:
        with patch("db_orders.get_connection", connection_factory):
            reserve_order_in_database(
                number,
                f"RESERVE-{number}",
                login,
                password,
            )
    except InjectedFailure as error:
        print(f"Искусственный сбой получен: {error}")
    else:
        raise RuntimeError("Контрольный сбой не возник.")

    if not failure_state["injected"]:
        raise RuntimeError("Тест не дошёл до изменения остатка.")

    after = read_snapshot(warehouse_id, order["id"])

    if after != before:
        raise RuntimeError("После отката состояние базы изменилось.")

    print(
        "ПРОЙДЕНО: остатки, статус, ключ резервирования, "
        "резервы и история восстановлены."
    )

    close_order_in_database(
        number,
        "cancel",
        "Завершение проверки отката",
        login,
        password,
    )


def main():
    print("=" * 76)
    print("ПРОВЕРКА ПАРАЛЛЕЛЬНОЙ РАБОТЫ И ОТКАТА POSTGRESQL")
    print("=" * 76)

    login = input("Логин менеджера: ").strip()
    password = getpass("Пароль менеджера: ")

    suffix = uuid4().hex[:8]
    warehouse_id, warehouse_name = create_test_warehouse(suffix)

    print(f"\nТестовый склад: {warehouse_name}")

    print("\n1. ДВА ЗАКАЗА ПО 6 СТОЛОВ ПРИ НАЛИЧИИ 8")

    check_concurrent_reservation(
        suffix, warehouse_id, warehouse_name, login, password
    )

    print("\n2. СБОЙ ПОСЛЕ ПЕРВОГО ИЗМЕНЕНИЯ ОСТАТКА")

    check_reservation_rollback(
        suffix, warehouse_id, warehouse_name, login, password
    )

    print("\nИТОГ: 2 проверки транзакций пройдены.")
    print("Склад «Основной» не использовался в этих проверках.")


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