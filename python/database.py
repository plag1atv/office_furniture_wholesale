import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"


def get_connection():
    """Открывает соединение с PostgreSQL."""
    load_dotenv(
        dotenv_path=ENV_FILE,
        encoding="utf-8-sig",
        override=False,
        interpolate=False,
    )

    required_variables = (
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
    )

    missing_variables = [
        name
        for name in required_variables
        if not os.getenv(name)
    ]

    if missing_variables:
        raise ValueError(
            "Не заполнены настройки подключения: "
            + ", ".join(missing_variables)
        )

    try:
        port = int(os.environ["DB_PORT"])
    except ValueError:
        raise ValueError("DB_PORT должен быть целым числом.") from None

    if not 1 <= port <= 65535:
        raise ValueError("DB_PORT должен находиться в диапазоне 1–65535.")

    return psycopg.connect(
        host=os.environ["DB_HOST"],
        port=port,
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=5,
        client_encoding="UTF8",
        application_name="office_furniture_wholesale",
        row_factory=dict_row,
    )