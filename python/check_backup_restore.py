import hashlib
import json
import sys

import psycopg
from psycopg import sql

from database import get_connection
from backup_comparison import normalize_constraints


def read_database_state(connection):
    """Читает структуру, содержимое таблиц и значения последовательностей."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
        )

        cursor.execute("SELECT current_database() AS name")
        database_name = cursor.fetchone()["name"]

        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        table_names = [
            row["table_name"] for row in cursor.fetchall()
        ]

        tables = {}

        for table_name in table_names:
            cursor.execute(
                sql.SQL("SELECT * FROM public.{}").format(
                    sql.Identifier(table_name)
                )
            )
            records = cursor.fetchall()

            serialized_records = sorted(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
                for record in records
            )

            content = "\n".join(serialized_records).encode("utf-8")

            tables[table_name] = {
                "count": len(records),
                "checksum": hashlib.sha256(content).hexdigest(),
            }

        cursor.execute(
            """
            SELECT
                table_name,
                ordinal_position,
                column_name,
                data_type,
                character_maximum_length,
                numeric_precision,
                numeric_scale,
                is_nullable,
                is_identity,
                identity_generation,
                column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
            """
        )
        columns = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                t.relname AS table_name,
                c.conname AS constraint_name,
                c.contype::text AS constraint_type,
                pg_get_constraintdef(c.oid, TRUE) AS definition,
                c.convalidated AS validated,
                c.conenforced AS enforced,
                c.condeferrable AS deferrable,
                c.condeferred AS initially_deferred
            FROM pg_constraint AS c
            JOIN pg_class AS t ON t.oid = c.conrelid
            JOIN pg_namespace AS n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public'
            ORDER BY t.relname, c.conname
            """
        )
        constraints = normalize_constraints(cursor.fetchall())

        cursor.execute(
            """
            SELECT tablename, indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
            ORDER BY tablename, indexname
            """
        )
        indexes = cursor.fetchall()

        cursor.execute(
            """
            SELECT sequencename
            FROM pg_sequences
            WHERE schemaname = 'public'
            ORDER BY sequencename
            """
        )
        sequence_names = [
            row["sequencename"] for row in cursor.fetchall()
        ]

        sequences = {}

        for sequence_name in sequence_names:
            cursor.execute(
                sql.SQL(
                    "SELECT last_value, is_called FROM public.{}"
                ).format(sql.Identifier(sequence_name))
            )
            sequences[sequence_name] = cursor.fetchone()

    return {
        "database_name": database_name,
        "tables": tables,
        "columns": columns,
        "constraints": constraints,
        "indexes": indexes,
        "sequences": sequences,
    }


def main():
    if len(sys.argv) != 2:
        raise ValueError("Передай имя восстановленной базы аргументом.")

    restore_name = sys.argv[1]

    if not restore_name.startswith("office_furniture_restore_"):
        raise ValueError("Ожидалось имя отдельной проверочной базы.")

    with get_connection() as connection:
        original = read_database_state(connection)

    if restore_name == original["database_name"]:
        raise ValueError("Нельзя сравнивать базу с самой собой.")

    with get_connection(database_name=restore_name) as connection:
        restored = read_database_state(connection)

    print("=" * 76)
    print("ПРОВЕРКА РЕЗЕРВНОЙ КОПИИ")
    print("=" * 76)
    print(f"Источник: {original['database_name']}")
    print(f"Восстановленная база: {restored['database_name']}")

    if len(original["tables"]) != 18:
        raise RuntimeError("В исходной базе ожидалось 18 таблиц.")

    if original["tables"].keys() != restored["tables"].keys():
        raise RuntimeError("Состав таблиц различается.")

    for name, expected in original["tables"].items():
        if restored["tables"][name] != expected:
            raise RuntimeError(f"Данные таблицы {name} различаются.")

        print(f"[OK] {name}: строк — {expected['count']}")

    for section in ("columns", "constraints", "indexes", "sequences"):
        if original[section] != restored[section]:
            raise RuntimeError(f"Обнаружено различие: {section}")

    print("\n[OK] Структура столбцов совпадает.")
    print("[OK] Ограничения и индексы совпадают.")
    print("[OK] Значения последовательностей совпадают.")
    print("\nИТОГ: резервная копия восстановлена и проверена.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, psycopg.Error) as error:
        print(f"\nПРОВЕРКА НЕ ПРОЙДЕНА: {error}")
        sys.exit(1)