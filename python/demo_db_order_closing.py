import sys
from getpass import getpass
from uuid import uuid4

import psycopg

from database import get_connection
from db_order_closing import close_order_in_database
from db_orders import (
    create_draft_order,
    register_payment_in_database,
    reserve_order_in_database,
)
from order_calculations import format_money


def create_reserved_demo_order(number, login, password):
    create_draft_order(
        number=number,
        customer_inn="0000000001",
        warehouse_name="Основной",
        items=[{"sku": "KR-01", "quantity": 1}],
        login=login,
        password=password,
    )

    reserve_order_in_database(
        number=number,
        operation_key=f"RESERVE-{number}",
        login=login,
        password=password,
    )


def main():
    print("=" * 66)
    print("ОТМЕНА И ИСТЕЧЕНИЕ РЕЗЕРВА В POSTGRESQL")
    print("=" * 66)

    manager_login = input("Логин менеджера: ").strip()
    manager_password = getpass("Пароль менеджера: ")

    accountant_login = input("Логин бухгалтера: ").strip()
    accountant_password = getpass("Пароль бухгалтера: ")

    suffix = uuid4().hex[:8]
    cancel_number = f"DEMO-CANCEL-{suffix}"
    expire_number = f"DEMO-EXPIRE-{suffix}"

    print("\n1. ОТМЕНА ЧАСТИЧНО ОПЛАЧЕННОГО ЗАКАЗА")

    create_reserved_demo_order(
        cancel_number, manager_login, manager_password
    )

    register_payment_in_database(
        number=cancel_number,
        amount="1000.00",
        external_ref=f"PAY-{cancel_number}",
        login=accountant_login,
        password=accountant_password,
    )

    result = close_order_in_database(
        number=cancel_number,
        action="cancel",
        reason="Учебная проверка отказа покупателя",
        login=manager_login,
        password=manager_password,
    )

    print(f"Заказ: {result['number']}")
    print(f"Статус: {result['status']}")
    print(f"Платежи сохранены: {format_money(result['paid'])}")
    print(f"Требуется урегулирование: {result['settlement_required']}")

    repeated = close_order_in_database(
        number=cancel_number,
        action="cancel",
        reason="Повторный запрос отмены",
        login=manager_login,
        password=manager_password,
    )

    if repeated["changed"]:
        raise RuntimeError("Повторная отмена изменила данные.")

    print("Повторная отмена не выполняла новых изменений.")

    print("\n2. ПРОВЕРКА ИСТЕЧЕНИЯ РЕЗЕРВА")

    create_reserved_demo_order(
        expire_number, manager_login, manager_password
    )

    # Только для этого нового демонстрационного заказа:
    # моделируем резерв, срок которого уже закончился.
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE public.reservations AS r
                SET created_at = clock_timestamp() - INTERVAL '2 hours',
                    expires_at = clock_timestamp() - INTERVAL '1 hour'
                FROM public.orders AS o
                WHERE r.order_id = o.id
                  AND o.number = %s
                  AND r.state = 'active'
                """,
                (expire_number,),
            )

    result = close_order_in_database(
        number=expire_number,
        action="expire",
        reason="Истёк срок учебного резерва",
        login=manager_login,
        password=manager_password,
    )

    if not result["changed"] or result["status"] != "draft":
        raise RuntimeError("Истёкший резерв не обработан.")

    print(f"Заказ: {result['number']}")
    print(f"Статус после истечения резерва: {result['status']}")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    p.sku,
                    sb.on_hand,
                    sb.reserved,
                    sb.on_hand - sb.reserved AS available
                FROM public.stock_balances AS sb
                JOIN public.products AS p ON p.id = sb.product_id
                JOIN public.warehouses AS w ON w.id = sb.warehouse_id
                WHERE w.name = 'Основной'
                  AND p.sku IN ('KR-01', 'ST-01')
                ORDER BY p.sku
                """
            )
            balances = cursor.fetchall()

    print("\nИТОГОВЫЕ ОСТАТКИ")

    for row in balances:
        print(
            f"{row['sku']}: наличие={row['on_hand']}, "
            f"резерв={row['reserved']}, доступно={row['available']}"
        )

    print("\nПроверки завершены.")


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