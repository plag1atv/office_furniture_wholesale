from authentication import authenticate_user, require_role
from database import get_connection
from order_calculations import validate_quantity


def load_locked_order(cursor, number):
    """Блокирует заголовок заказа до завершения транзакции."""
    cursor.execute(
        """
        SELECT id, number, warehouse_id, status
        FROM public.orders
        WHERE number = %s
        FOR UPDATE
        """,
        (number,),
    )
    order = cursor.fetchone()

    if order is None:
        raise ValueError("Заказ не найден.")

    return order


def load_order_items(cursor, order_id):
    cursor.execute(
        """
        SELECT oi.id, oi.product_id, oi.quantity, p.sku
        FROM public.order_items AS oi
        JOIN public.products AS p ON p.id = oi.product_id
        WHERE oi.order_id = %s
        ORDER BY oi.product_id
        """,
        (order_id,),
    )
    items = cursor.fetchall()

    if not items:
        raise ValueError("Заказ не содержит товаров.")

    return items


def add_history(cursor, order_id, old_status, new_status, user_id, reason):
    cursor.execute(
        """
        INSERT INTO public.order_history (
            order_id, old_status, new_status, changed_by, reason
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (order_id, old_status, new_status, user_id, reason),
    )


def prepare_order_for_shipment(number, picked_quantities, login, password):
    """Фиксирует комплектование и проверку подобранных товаров."""
    checked_quantities = {
        sku: validate_quantity(quantity)
        for sku, quantity in picked_quantities.items()
    }

    with get_connection() as connection:
        with connection.cursor() as cursor:
            user = authenticate_user(cursor, login, password)
            require_role(user, "warehouse")

            order = load_locked_order(cursor, number)
            items = load_order_items(cursor, order["id"])

            required_quantities = {
                item["sku"]: item["quantity"]
                for item in items
            }

            if checked_quantities != required_quantities:
                raise ValueError(
                    "Подобранные товары не совпадают с составом заказа."
                )

            if order["status"] not in (
                "paid", "picking", "ready", "completed"
            ):
                raise ValueError(
                    "Комплектование разрешено после полной оплаты."
                )

            if order["status"] == "paid":
                cursor.execute(
                    "UPDATE public.orders SET status = 'picking' WHERE id = %s",
                    (order["id"],),
                )

                add_history(
                    cursor,
                    order["id"],
                    "paid",
                    "picking",
                    user["id"],
                    "Заказ принят на комплектование",
                )
                order["status"] = "picking"

            if order["status"] == "picking":
                cursor.execute(
                    "UPDATE public.orders SET status = 'ready' WHERE id = %s",
                    (order["id"],),
                )

                add_history(
                    cursor,
                    order["id"],
                    "picking",
                    "ready",
                    user["id"],
                    "Состав и количество подобранных товаров проверены",
                )
                order["status"] = "ready"

            result = order["status"]

    return result


def ship_order_in_database(number, operation_key, login, password):
    """Атомарно записывает отгрузку, движения и изменение остатков."""
    if not isinstance(operation_key, str) or not operation_key.strip():
        raise ValueError("Необходимо указать ключ отгрузки.")

    operation_key = operation_key.strip()

    if len(operation_key) > 64:
        raise ValueError("Ключ отгрузки не должен превышать 64 символа.")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            user = authenticate_user(cursor, login, password)
            require_role(user, "warehouse")

            order = load_locked_order(cursor, number)
            items = load_order_items(cursor, order["id"])

            cursor.execute(
                """
                SELECT id, operation_key
                FROM public.shipments
                WHERE order_id = %s
                """,
                (order["id"],),
            )
            existing_shipment = cursor.fetchone()

            repeated = existing_shipment is not None

            if repeated:
                if order["status"] != "completed":
                    raise ValueError(
                        "Обнаружено несогласованное состояние отгрузки."
                    )

                if existing_shipment["operation_key"] != operation_key:
                    raise ValueError(
                        "Заказ уже отгружен. Новый ключ операции запрещён."
                    )

                shipment_id = existing_shipment["id"]
                before = []

            else:
                if order["status"] != "ready":
                    raise ValueError("Заказ ещё не готов к отгрузке.")

                cursor.execute(
                    """
                    SELECT
                        (SELECT sum(quantity * unit_price)
                         FROM public.order_items
                         WHERE order_id = %s) AS total,
                        (SELECT COALESCE(sum(amount), 0)
                         FROM public.payments
                         WHERE order_id = %s) AS paid
                    """,
                    (order["id"], order["id"]),
                )
                amounts = cursor.fetchone()

                if amounts["total"] != amounts["paid"]:
                    raise ValueError("Заказ оплачен не полностью.")

                # Проверяем собственный резерв каждой строки.
                for item in items:
                    cursor.execute(
                        """
                        SELECT id, quantity
                        FROM public.reservations
                        WHERE order_item_id = %s
                          AND state = 'active'
                        FOR UPDATE
                        """,
                        (item["id"],),
                    )
                    reservation = cursor.fetchone()

                    if (
                        reservation is None
                        or reservation["quantity"] != item["quantity"]
                    ):
                        raise ValueError(
                            f"Неверный резерв товара {item['sku']}."
                        )

                    item["reservation_id"] = reservation["id"]

                # Блокируем остатки в порядке product_id.
                before = []

                for item in items:
                    cursor.execute(
                        """
                        SELECT on_hand, reserved
                        FROM public.stock_balances
                        WHERE warehouse_id = %s AND product_id = %s
                        FOR UPDATE
                        """,
                        (order["warehouse_id"], item["product_id"]),
                    )
                    balance = cursor.fetchone()

                    if balance is None:
                        raise ValueError(
                            f"Нет остатка товара {item['sku']}."
                        )

                    if (
                        balance["on_hand"] < item["quantity"]
                        or balance["reserved"] < item["quantity"]
                    ):
                        raise ValueError(
                            f"Недостаточный запас или резерв {item['sku']}."
                        )

                    before.append(
                        {
                            "sku": item["sku"],
                            "on_hand": balance["on_hand"],
                            "reserved": balance["reserved"],
                            "available": (
                                balance["on_hand"] - balance["reserved"]
                            ),
                        }
                    )

                cursor.execute(
                    """
                    INSERT INTO public.shipments (
                        order_id, warehouse_id, operation_key, shipped_by
                    )
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        order["id"],
                        order["warehouse_id"],
                        operation_key,
                        user["id"],
                    ),
                )
                shipment_id = cursor.fetchone()["id"]

                for item in items:
                    cursor.execute(
                        """
                        INSERT INTO public.shipment_items (
                            shipment_id, order_id, warehouse_id,
                            order_item_id, product_id, quantity
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            shipment_id,
                            order["id"],
                            order["warehouse_id"],
                            item["id"],
                            item["product_id"],
                            item["quantity"],
                        ),
                    )
                    shipment_item_id = cursor.fetchone()["id"]

                    cursor.execute(
                        """
                        UPDATE public.stock_balances
                        SET on_hand = on_hand - %s,
                            reserved = reserved - %s
                        WHERE warehouse_id = %s AND product_id = %s
                        """,
                        (
                            item["quantity"],
                            item["quantity"],
                            order["warehouse_id"],
                            item["product_id"],
                        ),
                    )

                    cursor.execute(
                        """
                        UPDATE public.reservations
                        SET state = 'consumed',
                            closed_at = clock_timestamp()
                        WHERE id = %s
                        """,
                        (item["reservation_id"],),
                    )

                    cursor.execute(
                        """
                        INSERT INTO public.stock_movements (
                            warehouse_id, product_id, delta,
                            shipment_item_id, reason, created_by
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            order["warehouse_id"],
                            item["product_id"],
                            -item["quantity"],
                            shipment_item_id,
                            f"Отгрузка заказа {number}",
                            user["id"],
                        ),
                    )

                cursor.execute(
                    """
                    UPDATE public.orders
                    SET status = 'completed'
                    WHERE id = %s
                    """,
                    (order["id"],),
                )

                add_history(
                    cursor,
                    order["id"],
                    "ready",
                    "completed",
                    user["id"],
                    f"Выполнена отгрузка {operation_key}",
                )

            cursor.execute(
                """
                SELECT
                    p.sku,
                    sb.on_hand,
                    sb.reserved,
                    sb.on_hand - sb.reserved AS available
                FROM public.order_items AS oi
                JOIN public.products AS p ON p.id = oi.product_id
                JOIN public.stock_balances AS sb
                    ON sb.product_id = oi.product_id
                   AND sb.warehouse_id = %s
                WHERE oi.order_id = %s
                ORDER BY p.sku
                """,
                (order["warehouse_id"], order["id"]),
            )

            result = {
                "number": number,
                "shipment_id": shipment_id,
                "repeated": repeated,
                "before": before,
                "after": cursor.fetchall(),
            }

    return result