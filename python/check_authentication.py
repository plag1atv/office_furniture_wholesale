import sys
from getpass import getpass

import psycopg

from authentication import authenticate_user, require_role
from database import get_connection


def main():
    print("=" * 66)
    print("ПРОВЕРКА ВХОДА И ПРАВ ПОЛЬЗОВАТЕЛЯ")
    print("=" * 66)

    login = input("Логин пользователя приложения: ").strip()
    password = getpass("Пароль пользователя приложения: ")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            user = authenticate_user(cursor, login, password)

            print(f"\nВход выполнен: {user['login']}")
            print(f"Роли: {', '.join(user['roles']) or 'не назначены'}")

            require_role(user, "manager")

            print("Проверка роли менеджера пройдена.")
            print("Создание заказа разрешено.")

    print("\nПроверка завершена. Данные заказов не изменялись.")


if __name__ == "__main__":
    try:
        main()
    except PermissionError as error:
        print(f"\nДоступ запрещён: {error}")
        sys.exit(1)
    except (ValueError, psycopg.Error, EOFError) as error:
        print(f"\nОшибка: {error}")
        sys.exit(1)