import sys
from getpass import getpass

import psycopg

from db_orders import register_payment_in_database
from order_calculations import format_money


def print_payment_result(result):
    print("-" * 66)
    print(f"Заказ: {result['number']}")
    print(f"Платёж: {result['external_ref']}")

    if result["already_registered"]:
        print("Повторный запрос: новый платёж не создан.")
    else:
        print("Платёж зарегистрирован.")

    print(f"Статус: {result['status']}")
    print(f"Стоимость: {format_money(result['total'])}")
    print(f"Всего оплачено: {format_money(result['paid'])}")
    print(f"Осталось оплатить: {format_money(result['remaining'])}")


def main():
    print("=" * 66)
    print("РЕГИСТРАЦИЯ ПЛАТЕЖЕЙ В POSTGRESQL")
    print("=" * 66)

    login = input("Логин бухгалтера: ").strip()
    password = getpass("Пароль бухгалтера: ")

    print("\n1. ЧАСТИЧНАЯ ОПЛАТА")

    result = register_payment_in_database(
        number="DB-ORD-001",
        amount="35000.00",
        external_ref="PAY-DB-ORD-001-01",
        login=login,
        password=password,
    )
    print_payment_result(result)

    print("\n2. ПОВТОР ПЕРВОГО ПЛАТЕЖА")

    result = register_payment_in_database(
        number="DB-ORD-001",
        amount="35000.00",
        external_ref="PAY-DB-ORD-001-01",
        login=login,
        password=password,
    )
    print_payment_result(result)

    print("\n3. ДОПЛАТА")

    result = register_payment_in_database(
        number="DB-ORD-001",
        amount="37500.00",
        external_ref="PAY-DB-ORD-001-02",
        login=login,
        password=password,
    )
    print_payment_result(result)


if __name__ == "__main__":
    try:
        main()
    except (PermissionError, ValueError, psycopg.Error, EOFError) as error:
        print(f"\nОшибка: {error}")
        sys.exit(1)