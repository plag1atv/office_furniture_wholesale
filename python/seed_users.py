import hashlib
import secrets
import sys
from getpass import getpass

import psycopg

from database import get_connection


PASSWORD_ITERATIONS = 600_000

DEMO_USERS = (
    ("manager", "manager"),
    ("accountant", "accountant"),
    ("warehouse", "warehouse"),
    ("admin", "admin"),
)


def hash_password(password):
    """Создаёт хеш пароля со случайной солью."""
    salt = secrets.token_bytes(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )

    return (
        f"pbkdf2_sha256${PASSWORD_ITERATIONS}"
        f"${salt.hex()}${digest.hex()}"
    )


def request_password(login):
    """Запрашивает пароль нового пользователя без отображения."""
    while True:
        print(f"\nНовый пользователь: {login}")

        password = getpass("Придумай пароль, не менее 12 символов: ")
        confirmation = getpass("Повтори пароль: ")

        if len(password) < 12:
            print("Пароль слишком короткий. Повтори ввод.")
            continue

        if password != confirmation:
            print("Пароли не совпали. Повтори ввод.")
            continue

        return password


def seed_users(connection):
    """Создаёт пользователей и назначает роли."""
    with connection.cursor() as cursor:
        for login, role_name in DEMO_USERS:
            cursor.execute(
                """
                INSERT INTO public.roles (name)
                VALUES (%s)
                ON CONFLICT (name) DO NOTHING
                """,
                (role_name,),
            )

            cursor.execute(
                """
                SELECT id
                FROM public.roles
                WHERE name = %s
                """,
                (role_name,),
            )
            role_id = cursor.fetchone()["id"]

            cursor.execute(
                """
                SELECT id
                FROM public.users
                WHERE login = %s
                """,
                (login,),
            )
            existing_user = cursor.fetchone()

            if existing_user is None:
                password = request_password(login)
                password_hash = hash_password(password)
                del password

                cursor.execute(
                    """
                    INSERT INTO public.users (
                        login,
                        password_hash,
                        active
                    )
                    VALUES (%s, %s, TRUE)
                    RETURNING id
                    """,
                    (login, password_hash),
                )
                user_id = cursor.fetchone()["id"]

                print(f"Пользователь {login} подготовлен к сохранению.")
            else:
                user_id = existing_user["id"]
                print(f"Пользователь {login} уже существует.")

            cursor.execute(
                """
                INSERT INTO public.user_roles (user_id, role_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, role_id) DO NOTHING
                """,
                (user_id, role_id),
            )


def print_users(connection):
    """Показывает пользователей и роли без паролей и хешей."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                u.login,
                u.active,
                string_agg(r.name, ', ' ORDER BY r.name) AS roles
            FROM public.users AS u
            JOIN public.user_roles AS ur
                ON ur.user_id = u.id
            JOIN public.roles AS r
                ON r.id = ur.role_id
            WHERE u.login = ANY(%s)
            GROUP BY u.id, u.login, u.active
            ORDER BY u.login
            """,
            ([login for login, role in DEMO_USERS],),
        )

        users = cursor.fetchall()

        if len(users) != len(DEMO_USERS):
            raise ValueError("Не все учебные пользователи найдены.")

        print("\nПОЛЬЗОВАТЕЛИ ПРИЛОЖЕНИЯ")
        print("-" * 66)

        for user in users:
            state = "активен" if user["active"] else "отключён"
            print(
                f"{user['login']:<15}"
                f"{user['roles']:<20}"
                f"{state}"
            )

        print("-" * 66)


def main():
    print("=" * 66)
    print("СОЗДАНИЕ ПОЛЬЗОВАТЕЛЕЙ И РОЛЕЙ")
    print("=" * 66)

    with get_connection() as connection:
        seed_users(connection)

    print("\nПользователи и назначения ролей сохранены.")

    with get_connection() as connection:
        print_users(connection)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, psycopg.Error, EOFError) as error:
        print(f"\nОшибка: {error}")
        sys.exit(1)