import sys

import psycopg

from database import get_connection


def seed_reference_data(connection):
    """Добавляет вымышленные справочные данные без удаления существующих."""
    with connection.cursor() as cursor:
        # Покупатель.
        cursor.execute(
            """
            INSERT INTO public.customers (name, inn, address)
            VALUES (%s, %s, %s)
            ON CONFLICT (inn) DO NOTHING
            """,
            (
                'ООО «Учебный офис»',
                "0000000001",
                "Учебный адрес покупателя",
            ),
        )

        # Поставщик.
        cursor.execute(
            """
            INSERT INTO public.suppliers (name, inn)
            VALUES (%s, %s)
            ON CONFLICT (inn) DO NOTHING
            """,
            (
                'ООО «Учебная мебель»',
                "0000000002",
            ),
        )

        cursor.execute(
            """
            SELECT id
            FROM public.suppliers
            WHERE inn = %s
            """,
            ("0000000002",),
        )
        supplier_id = cursor.fetchone()["id"]

        # Категории.
        categories = ("Столы", "Кресла")

        for category_name in categories:
            cursor.execute(
                """
                INSERT INTO public.categories (name)
                VALUES (%s)
                ON CONFLICT (name) DO NOTHING
                """,
                (category_name,),
            )

        # Товары: артикул, название, категория, цена.
        products = [
            ("ST-01", "Стол офисный", "Столы", "12500.00"),
            ("KR-01", "Кресло офисное", "Кресла", "8750.00"),
        ]

        for sku, name, category_name, price in products:
            cursor.execute(
                """
                SELECT id
                FROM public.categories
                WHERE name = %s
                """,
                (category_name,),
            )
            category_id = cursor.fetchone()["id"]

            cursor.execute(
                """
                INSERT INTO public.products (
                    category_id,
                    supplier_id,
                    sku,
                    name,
                    price
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (sku) DO NOTHING
                """,
                (category_id, supplier_id, sku, name, price),
            )

        # Склад.
        cursor.execute(
            """
            INSERT INTO public.warehouses (name, address)
            VALUES (%s, %s)
            ON CONFLICT (name) DO NOTHING
            """,
            ("Основной", "Учебный адрес склада"),
        )

        cursor.execute(
            """
            SELECT id
            FROM public.warehouses
            WHERE name = %s
            """,
            ("Основной",),
        )
        warehouse_id = cursor.fetchone()["id"]

        # Начальные остатки.
        initial_quantities = [
            ("ST-01", 10),
            ("KR-01", 20),
        ]

        for sku, on_hand in initial_quantities:
            cursor.execute(
                """
                SELECT id
                FROM public.products
                WHERE sku = %s
                """,
                (sku,),
            )
            product_id = cursor.fetchone()["id"]

            cursor.execute(
                """
                INSERT INTO public.stock_balances (
                    warehouse_id,
                    product_id,
                    on_hand,
                    reserved
                )
                VALUES (%s, %s, %s, 0)
                ON CONFLICT (warehouse_id, product_id) DO NOTHING
                """,
                (warehouse_id, product_id, on_hand),
            )


def print_reference_data(connection):
    """Показывает сохранённые товары и складские остатки."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                p.sku,
                p.name,
                p.price,
                w.name AS warehouse_name,
                sb.on_hand,
                sb.reserved,
                sb.on_hand - sb.reserved AS available
            FROM public.stock_balances AS sb
            JOIN public.products AS p
                ON p.id = sb.product_id
            JOIN public.warehouses AS w
                ON w.id = sb.warehouse_id
            WHERE w.name = %s
              AND p.sku IN (%s, %s)
            ORDER BY p.sku
            """,
            ("Основной", "KR-01", "ST-01"),
        )

        records = cursor.fetchall()

        if len(records) != 2:
            raise ValueError("Не найдены обе учебные товарные позиции.")

        print("\nТОВАРЫ И ОСТАТКИ В POSTGRESQL")
        print("-" * 76)

        for record in records:
            print(f"\nАртикул: {record['sku']}")
            print(f"Название: {record['name']}")
            print(f"Цена: {record['price']:.2f} руб.")
            print(f"Склад: {record['warehouse_name']}")
            print(f"В наличии: {record['on_hand']}")
            print(f"В резерве: {record['reserved']}")
            print(f"Доступно: {record['available']}")

        print("\n" + "-" * 76)


def main():
    print("=" * 76)
    print("ПОДГОТОВКА УЧЕБНЫХ ДАННЫХ")
    print("=" * 76)

    # Все добавления выполняются в одной транзакции.
    with get_connection() as connection:
        seed_reference_data(connection)

    print("Учебные данные сохранены.")

    # Проверяем результат через новое соединение.
    with get_connection() as connection:
        print_reference_data(connection)

    print("Проверка сохранённых данных завершена.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, psycopg.Error) as error:
        print(f"\nОшибка: {error}")
        sys.exit(1)