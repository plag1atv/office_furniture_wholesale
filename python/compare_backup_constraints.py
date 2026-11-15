from collections import Counter

from database import get_connection


RESTORED_DATABASE = "office_furniture_restore_20261115_213838"


def read_constraints(database_name=None):
    with get_connection(database_name=database_name) as connection:
        with connection.cursor() as cursor:
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
            return cursor.fetchall()


def semantic_key(record):
    """Содержание ограничения без его имени."""
    return (
        record["table_name"],
        record["constraint_type"],
        record["definition"],
        record["validated"],
        record["enforced"],
        record["deferrable"],
        record["initially_deferred"],
    )


def print_differences(title, records):
    print(f"\n{title}: {len(records)}")

    for record in records[:10]:
        print(
            f"{record['table_name']} | "
            f"{record['constraint_name']} | "
            f"тип={record['constraint_type']} | "
            f"{record['definition']} | "
            f"validated={record['validated']} | "
            f"enforced={record['enforced']}"
        )

    if len(records) > 10:
        print("Показаны первые 10 различий.")


def main():
    original = read_constraints()
    restored = read_constraints(RESTORED_DATABASE)

    print(f"Ограничений в исходной базе: {len(original)}")
    print(f"Ограничений в восстановленной базе: {len(restored)}")

    original_only = [
        record for record in original if record not in restored
    ]
    restored_only = [
        record for record in restored if record not in original
    ]

    print_differences("Только в исходной базе", original_only)
    print_differences("Только в восстановленной базе", restored_only)

    original_meaning = Counter(map(semantic_key, original))
    restored_meaning = Counter(map(semantic_key, restored))

    print()

    if original == restored:
        print("Ограничения полностью совпадают.")
    elif original_meaning == restored_meaning:
        print(
            "Содержание ограничений совпадает. "
            "Различаются только имена или порядок записей."
        )
    else:
        print("Обнаружены различия в содержании ограничений.")


if __name__ == "__main__":
    main()