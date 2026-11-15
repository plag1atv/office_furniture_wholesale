from authentication import authenticate_user, require_role
from database import get_connection
from db_warehouse import (
    add_history,
    load_locked_order,
    load_order_items,
)


def close_order_in_database(
    number,
    action,
    reason,
    login,
    password,
):
    """
    action='cancel': отменяет заказ и снимает резерв.
    action='expire': снимает истёкший неоплаченный резерв
    и возвращает заказ в черновик.

    Подтверждённые платежи сохраняются.
    """
    if action not in ("cancel", "expire"):
        raise ValueError("Неизвестный вид операции.")

    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Необходимо указать причину операции.")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            user = authenticate_user(cursor, login, password)
            require_role(user, "manager")

            order = load_locked_order(cursor, number)

            cursor.execute(
                "SELECT manager_id FROM public.orders WHERE id = %s",
                (order["id"],),
            )
            manager_id = cursor.fetchone()["manager_id"]

            if manager_id != user["id"]:
                raise PermissionError("Заказ закреплён за другим менеджером.")

            old_status = order["status"]
            new_status = old_status
            changed = False

            if action == "cancel":
                if old_status == "completed":
                    raise ValueError("Отгруженный заказ отменить нельзя.")

                if old_status not in (
                    "draft",
                    "awaiting_payment",
                    "paid",
                    "picking",
                    "ready",
                    "cancelled",
                ):
                    raise ValueError("Недопустимое состояние заказа.")

                changed = old_status != "cancelled"
                new_status = "cancelled"

            elif old_status == "awaiting_payment":
                changed = True
                new_status = "draft"

            cursor.execute(
                """
                SELECT id, order_item_id, product_id, quantity, expires_at
                FROM public.reservations
                WHERE order_id = %s AND state = 'active'
                ORDER BY product_id
                FOR UPDATE
                """,
                (order["id"],),
            )
            reservations = cursor.fetchall()

            if changed:
                if old_status == "draft":
                    if reservations:
                        raise ValueError(
                            "У черновика обнаружен неожиданный активный резерв."
                        )
                else:
                    items = load_order_items(cursor, order["id"])

                    expected = {
                        item["id"]: item["quantity"]
                        for item in items
                    }
                    actual = {
                        row["order_item_id"]: row["quantity"]
                        for row in reservations
                    }

                    if actual != expected:
                        raise ValueError(
                            "Активные резервы не соответствуют строкам заказа."
                        )

                if action == "expire":
                    cursor.execute(
                        "SELECT clock_timestamp() AS checked_at"
                    )
                    checked_at = cursor.fetchone()["checked_at"]

                    if not any(
                        row["expires_at"] <= checked_at
                        for row in reservations
                    ):
                        changed = False
                        new_status = old_status

            if changed:
                # Сначала блокируем и проверяем все складские записи.
                for reservation in reservations:
                    cursor.execute(
                        """
                        SELECT reserved
                        FROM public.stock_balances
                        WHERE warehouse_id = %s AND product_id = %s
                        FOR UPDATE
                        """,
                        (
                            order["warehouse_id"],
                            reservation["product_id"],
                        ),
                    )
                    balance = cursor.fetchone()

                    if (
                        balance is None
                        or balance["reserved"] < reservation["quantity"]
                    ):
                        raise ValueError(
                            "Складской резерв не соответствует данным заказа."
                        )

                closed_state = (
                    "released" if action == "cancel" else "expired"
                )

                for reservation in reservations:
                    cursor.execute(
                        """
                        UPDATE public.stock_balances
                        SET reserved = reserved - %s
                        WHERE warehouse_id = %s AND product_id = %s
                        """,
                        (
                            reservation["quantity"],
                            order["warehouse_id"],
                            reservation["product_id"],
                        ),
                    )

                    cursor.execute(
                        """
                        UPDATE public.reservations
                        SET state = %s,
                            closed_at = clock_timestamp()
                        WHERE id = %s
                        """,
                        (closed_state, reservation["id"]),
                    )

                cursor.execute(
                    "UPDATE public.orders SET status = %s WHERE id = %s",
                    (new_status, order["id"]),
                )

                add_history(
                    cursor,
                    order["id"],
                    old_status,
                    new_status,
                    user["id"],
                    reason.strip(),
                )

            cursor.execute(
                """
                SELECT COALESCE(sum(amount), 0) AS paid
                FROM public.payments
                WHERE order_id = %s
                """,
                (order["id"],),
            )
            paid = cursor.fetchone()["paid"]

            result = {
                "number": number,
                "status": new_status,
                "changed": changed,
                "paid": paid,
                "settlement_required": (
                    new_status == "cancelled" and paid > 0
                ),
            }

    return result