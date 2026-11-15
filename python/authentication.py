import hashlib
import hmac


PASSWORD_ITERATIONS = 600_000


def verify_password(password, stored_hash):
    """Сравнивает пароль с хешем, созданным seed_users.py."""
    try:
        algorithm, iterations_text, salt_hex, digest_hex = (
            stored_hash.split("$")
        )

        if algorithm != "pbkdf2_sha256":
            return False

        iterations = int(iterations_text)

        if iterations != PASSWORD_ITERATIONS:
            return False

        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)

        if len(salt) != 16 or len(expected_digest) != 32:
            return False

    except (ValueError, TypeError, AttributeError):
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )

    return hmac.compare_digest(actual_digest, expected_digest)


def authenticate_user(cursor, login, password):
    """Проверяет пользователя и возвращает его идентификатор и роли."""
    cursor.execute(
        """
        SELECT id, login, password_hash, active
        FROM public.users
        WHERE login = %s
        """,
        (login.strip(),),
    )

    user = cursor.fetchone()

    if user is None:
        raise PermissionError("Неверный логин или пароль.")

    if not verify_password(password, user["password_hash"]):
        raise PermissionError("Неверный логин или пароль.")

    if not user["active"]:
        raise PermissionError("Учётная запись отключена.")

    cursor.execute(
        """
        SELECT r.name
        FROM public.roles AS r
        JOIN public.user_roles AS ur
            ON ur.role_id = r.id
        WHERE ur.user_id = %s
        ORDER BY r.name
        """,
        (user["id"],),
    )

    roles = tuple(record["name"] for record in cursor.fetchall())

    return {
        "id": user["id"],
        "login": user["login"],
        "roles": roles,
    }


def require_role(user, role_name):
    """Запрещает операцию при отсутствии требуемой роли."""
    if role_name not in user["roles"]:
        raise PermissionError(
            f"Для выполнения операции требуется роль: {role_name}."
        )