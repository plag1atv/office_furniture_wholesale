import sys

import psycopg

from database import get_connection


def main():
    print("=" * 66)
    print("ПРОВЕРКА ПОДКЛЮЧЕНИЯ К POSTGRESQL")
    print("=" * 66)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    current_database() AS database_name,
                    current_user AS database_user,
                    current_setting('server_version') AS server_version,
                    current_setting('server_encoding') AS server_encoding
                """
            )

            information = cursor.fetchone()

            print(f"База данных: {information['database_name']}")
            print(f"Пользователь: {information['database_user']}")
            print(f"Версия сервера: {information['server_version']}")
            print(f"Кодировка базы: {information['server_encoding']}")

            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            )

            tables = cursor.fetchall()

            print(f"\nКоличество таблиц: {len(tables)}")
            print("\nТАБЛИЦЫ ПРОЕКТА")

            for table in tables:
                print(f"  {table['table_name']}")

            if len(tables) != 18:
                raise ValueError(
                    f"Ожидалось 18 таблиц, обнаружено {len(tables)}."
                )

    print("\nПодключение работает. Все 18 таблиц доступны.")
    print("Соединение с базой закрыто.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, psycopg.Error) as error:
        print(f"\nОшибка проверки: {error}")
        sys.exit(1)