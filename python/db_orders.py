from decimal import Decimal
from authentication import authenticate_user, require_role
from database import get_connection
from order_calculations import (
    calculate_order_total,
    validate_quantity,
)


def normalize_items(items):
    """Проверяет строки и объединяет повторяющиеся артикулы."""
    if not items:
        raise ValueError("Заказ должен содержать хотя бы один товар.")

    quantities = {}

    for item in items:
        sku = item["sku"]

        if not isinstance(sku, str) or not sku.strip():
            raise ValueError("Необходимо указать артикул товара.")

        sku = sku.strip().upper()
        quantity = validate_quantity(item["quantity"])

        quantities[sku] = quantities.get(sku, 0) + quantity

        if quantities[sku] > 2_147_483_647:
            raise ValueError(f"Слишком большое количество товара {sku}.")

    return quantities


def create_draft_order(
    number,
    customer_inn,
    warehouse_name,
    items,
    login,
    password,
):
    """Создаёт черновик заказа вместе со строками и историей."""
    if not isinstance(number, str) or not number.strip():
        raise ValueError("Необходимо указать номер заказа.")

    number = number.strip()

    if len(number) > 40:
        raise ValueError("Номер заказа не должен превышать 40 символов.")

    required_quantities = normalize_items(items)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            user = authenticate_user(cursor, login, password)
            require_role(user, "manager")

            cursor.execute(
                """
                SELECT id
                FROM public.orders
                WHERE number = %s
                """,
                (number,),
            )

            if cursor.fetchone() is not None:
                raise ValueError(f"Заказ {number} уже существует.")

            cursor.execute(
                """
                SELECT id, name
                FROM public.customers
                WHERE inn = %s AND active = TRUE
                """,
                (customer_inn,),
            )
            customer = cursor.fetchone()

            if customer is None:
                raise ValueError("Активный покупатель с таким ИНН не найден.")

            cursor.execute(
                """
                SELECT id, name
                FROM public.warehouses
                WHERE name = %s
                """,
                (warehouse_name,),
            )
            warehouse = cursor.fetchone()

            if warehouse is None:
                raise ValueError("Указанный склад не найден.")

            order_items = []

            for sku, quantity in sorted(required_quantities.items()):
                cursor.execute(
                    """
                    SELECT id, sku, name, price
                    FROM public.products
                    WHERE sku = %s AND active = TRUE
                    """,
                    (sku,),
                )
                product = cursor.fetchone()

                if product is None:
                    raise ValueError(f"Активный товар {sku} не найден.")

                order_items.append(
                    {
                        "product_id": product["id"],
                        "sku": product["sku"],
                        "name": product["name"],
                        "quantity": quantity,
                        "unit_price": product["price"],
                    }
                )

            total = calculate_order_total(order_items)

            if total > Decimal("999999999999.99"):
                raise ValueError("Сумма заказа превышает допустимое значение.")

            cursor.execute(
                """
                INSERT INTO public.orders (
                    number,
                    customer_id,
                    warehouse_id,
                    manager_id,
                    status
                )
                VALUES (%s, %s, %s, %s, 'draft')
                RETURNING id, number, status
                """,
                (
                    number,
                    customer["id"],
                    warehouse["id"],
                    user["id"],
                ),
            )
            order = cursor.fetchone()

            for item in order_items:
                cursor.execute(
                    """
                    INSERT INTO public.order_items (
                        order_id,
                        product_id,
                        quantity,
                        unit_price
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        order["id"],
                        item["product_id"],
                        item["quantity"],
                        item["unit_price"],
                    ),
                )

            cursor.execute(
                """
                INSERT INTO public.order_history (
                    order_id,
                    old_status,
                    new_status,
                    changed_by,
                    reason
                )
                VALUES (%s, NULL, 'draft', %s, %s)
                """,
                (
                    order["id"],
                    user["id"],
                    "Создан черновик заказа",
                ),
            )

            result = {
                "id": order["id"],
                "number": order["number"],
                "status": order["status"],
                "customer": customer["name"],
                "warehouse": warehouse["name"],
                "manager": user["login"],
                "items": order_items,
                "total": total,
            }

    # Возвращаем результат только после успешной фиксации транзакции.
    return result