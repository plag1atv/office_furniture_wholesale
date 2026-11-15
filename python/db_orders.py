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


def reserve_order_in_database(number, operation_key, login, password):
    """Резервирует все строки заказа одной транзакцией."""
    if not isinstance(operation_key, str) or not operation_key.strip():
        raise ValueError("Необходимо указать ключ резервирования.")

    operation_key = operation_key.strip()

    if len(operation_key) > 64:
        raise ValueError("Ключ резервирования не должен превышать 64 символа.")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            user = authenticate_user(cursor, login, password)
            require_role(user, "manager")

            # Все операции изменения заказа должны начинаться
            # с блокировки его заголовка.
            cursor.execute(
                """
                SELECT id, number, warehouse_id, manager_id,
                       status, reserve_key
                FROM public.orders
                WHERE number = %s
                FOR UPDATE
                """,
                (number,),
            )
            order = cursor.fetchone()

            if order is None:
                raise ValueError("Заказ не найден.")

            if order["manager_id"] != user["id"]:
                raise PermissionError("Заказ закреплён за другим менеджером.")

            already_reserved = (
                order["status"] == "awaiting_payment"
                and order["reserve_key"] == operation_key
            )

            if not already_reserved:
                if order["status"] != "draft":
                    raise ValueError(
                        "Резервирование разрешено только для черновика."
                    )

                cursor.execute(
                    """
                    SELECT
                        oi.id,
                        oi.product_id,
                        oi.quantity,
                        p.sku
                    FROM public.order_items AS oi
                    JOIN public.products AS p
                        ON p.id = oi.product_id
                    WHERE oi.order_id = %s
                    ORDER BY oi.product_id
                    """,
                    (order["id"],),
                )
                items = cursor.fetchall()

                if not items:
                    raise ValueError("Заказ не содержит товаров.")

                # Получаем блокировки в одинаковом порядке product_id.
                # До завершения всех проверок остатки не изменяем.
                for item in items:
                    cursor.execute(
                        """
                        SELECT on_hand, reserved
                        FROM public.stock_balances
                        WHERE warehouse_id = %s
                          AND product_id = %s
                        FOR UPDATE
                        """,
                        (order["warehouse_id"], item["product_id"]),
                    )
                    balance = cursor.fetchone()

                    if balance is None:
                        raise ValueError(
                            f"Нет складской записи для товара {item['sku']}."
                        )

                    available = balance["on_hand"] - balance["reserved"]

                    if item["quantity"] > available:
                        raise ValueError(
                            f"Недостаточно товара {item['sku']}: "
                            f"требуется {item['quantity']}, "
                            f"доступно {available}."
                        )

                cursor.execute(
                    """
                    SELECT
                        clock_timestamp() + INTERVAL '24 hours'
                        AS expires_at
                    """
                )
                expires_at = cursor.fetchone()["expires_at"]

                for item in items:
                    cursor.execute(
                        """
                        UPDATE public.stock_balances
                        SET reserved = reserved + %s
                        WHERE warehouse_id = %s
                          AND product_id = %s
                        """,
                        (
                            item["quantity"],
                            order["warehouse_id"],
                            item["product_id"],
                        ),
                    )

                    cursor.execute(
                        """
                        INSERT INTO public.reservations (
                            order_item_id,
                            order_id,
                            warehouse_id,
                            product_id,
                            quantity,
                            state,
                            expires_at
                        )
                        VALUES (%s, %s, %s, %s, %s, 'active', %s)
                        """,
                        (
                            item["id"],
                            order["id"],
                            order["warehouse_id"],
                            item["product_id"],
                            item["quantity"],
                            expires_at,
                        ),
                    )

                cursor.execute(
                    """
                    UPDATE public.orders
                    SET status = 'awaiting_payment',
                        reserve_key = %s
                    WHERE id = %s
                    """,
                    (operation_key, order["id"]),
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
                    VALUES (
                        %s, 'draft', 'awaiting_payment', %s, %s
                    )
                    """,
                    (
                        order["id"],
                        user["id"],
                        "Создан резерв всех строк заказа",
                    ),
                )

            cursor.execute(
                """
                SELECT
                    p.sku,
                    r.quantity AS order_reserved,
                    sb.on_hand,
                    sb.reserved,
                    sb.on_hand - sb.reserved AS available
                FROM public.reservations AS r
                JOIN public.products AS p
                    ON p.id = r.product_id
                JOIN public.stock_balances AS sb
                    ON sb.warehouse_id = r.warehouse_id
                   AND sb.product_id = r.product_id
                WHERE r.order_id = %s
                  AND r.state = 'active'
                ORDER BY p.sku
                """,
                (order["id"],),
            )
            balances = cursor.fetchall()

            result = {
                "number": order["number"],
                "status": "awaiting_payment",
                "already_reserved": already_reserved,
                "balances": balances,
            }

    return result