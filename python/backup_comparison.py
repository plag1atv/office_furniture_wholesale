ORDER_STATUSES = (
    "draft",
    "awaiting_payment",
    "paid",
    "picking",
    "ready",
    "completed",
    "cancelled",
)

RESERVATION_STATES = (
    "active",
    "released",
    "consumed",
    "expired",
)

KNOWN_CHECKS = {
    ("orders", "ck_orders_status"): (
        "status", ORDER_STATUSES, False
    ),
    ("order_history", "ck_history_new_status"): (
        "new_status", ORDER_STATUSES, False
    ),
    ("order_history", "ck_history_old_status"): (
        "old_status", ORDER_STATUSES, True
    ),
    ("reservations", "ck_reservations_state"): (
        "state", RESERVATION_STATES, False
    ),
}


def expected_definitions(column, values, allow_null):
    """Возвращает два известных равнозначных SQL-представления."""
    array_cast = (
        "ARRAY["
        + ", ".join(
            f"'{value}'::character varying"
            for value in values
        )
        + "]::text[]"
    )

    element_cast = (
        "ARRAY["
        + ", ".join(
            f"'{value}'::character varying::text"
            for value in values
        )
        + "]"
    )

    definitions = set()

    for array_expression in (array_cast, element_cast):
        expression = f"{column}::text = ANY ({array_expression})"

        if allow_null:
            expression = f"{column} IS NULL OR ({expression})"

        definitions.add(f"CHECK ({expression})")

    return definitions


def normalize_constraints(records):
    """
    Нормализует только четыре проверенных CHECK-ограничения.
    Имена, типы и остальные свойства сохраняются.
    """
    normalized = []

    for record in records:
        item = record.copy()
        key = (item["table_name"], item["constraint_name"])

        if key in KNOWN_CHECKS:
            column, values, allow_null = KNOWN_CHECKS[key]

            accepted = expected_definitions(
                column, values, allow_null
            )

            if item["definition"] not in accepted:
                raise RuntimeError(
                    "Неизвестное определение ограничения "
                    f"{key[0]}.{key[1]}: "
                    f"{item['definition']}"
                )

            item["definition"] = (
                f"ENUM_CHECK|{column}|"
                f"allow_null={allow_null}|"
                + ",".join(values)
            )

        normalized.append(item)

    return sorted(
        normalized,
        key=lambda item: (
            item["table_name"],
            item["constraint_name"],
        ),
    )