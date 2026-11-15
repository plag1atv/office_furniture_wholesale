from copy import deepcopy
from decimal import Decimal

from inventory import reserve_order
from order_calculations import (
    calculate_order_total,
    create_order_item,
    parse_price,
)


STATUS_DRAFT = "Черновик"
STATUS_AWAITING_PAYMENT = "Ожидает оплаты"
STATUS_PAID = "Оплачен"
STATUS_PICKING = "Комплектуется"


def create_order(number, customer, items):
    """Создаёт заказ в состоянии черновика."""
    if not isinstance(number, str) or not number.strip():
        raise ValueError("Необходимо указать номер заказа.")

    if not isinstance(customer, str) or not customer.strip():
        raise ValueError("Необходимо указать покупателя.")

    checked_items = [
        create_order_item(
            sku=item["sku"],
            name=item["name"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
        )
        for item in items
    ]

    total = calculate_order_total(checked_items)

    return {
        "number": number.strip(),
        "customer": customer.strip(),
        "items": checked_items,
        "total": total,
        "status": STATUS_DRAFT,
        "payments": [],
        "history": [
            {
                "action": "Создание заказа",
                "status": STATUS_DRAFT,
            }
        ],
    }


def confirm_order(order, stock):
    """Резервирует товары и переводит заказ в ожидание оплаты."""
    if order["status"] != STATUS_DRAFT:
        raise ValueError("Подтвердить можно только черновик заказа.")

    updated_stock = reserve_order(order["items"], stock)
    updated_order = deepcopy(order)

    updated_order["status"] = STATUS_AWAITING_PAYMENT
    updated_order["history"].append(
        {
            "action": "Товары зарезервированы",
            "status": STATUS_AWAITING_PAYMENT,
        }
    )

    return updated_order, updated_stock


def get_paid_amount(order):
    """Возвращает общую сумму зарегистрированных платежей."""
    return sum(
        (payment["amount"] for payment in order["payments"]),
        Decimal("0.00"),
    )


def get_remaining_amount(order):
    """Возвращает неоплаченную часть стоимости заказа."""
    return order["total"] - get_paid_amount(order)


def register_payment(order, amount, external_ref):
    """Регистрирует платёж с уникальным для заказа номером."""
    if order["status"] != STATUS_AWAITING_PAYMENT:
        raise ValueError(
            "Принимать оплату можно только для заказа, ожидающего оплаты."
        )

    if not isinstance(external_ref, str) or not external_ref.strip():
        raise ValueError("Необходимо указать номер платёжного документа.")

    payment_ref = external_ref.strip()

    for payment in order["payments"]:
        if payment["external_ref"] == payment_ref:
            raise ValueError(
                f"Платёж {payment_ref} уже зарегистрирован."
            )

    payment_amount = parse_price(amount)

    if payment_amount <= 0:
        raise ValueError("Сумма платежа должна быть больше нуля.")

    if payment_amount > get_remaining_amount(order):
        raise ValueError("Сумма платежа превышает остаток к оплате.")

    updated_order = deepcopy(order)

    updated_order["payments"].append(
        {
            "external_ref": payment_ref,
            "amount": payment_amount,
        }
    )

    if get_remaining_amount(updated_order) == Decimal("0.00"):
        updated_order["status"] = STATUS_PAID

    updated_order["history"].append(
        {
            "action": f"Зарегистрирован платёж {payment_ref}",
            "status": updated_order["status"],
        }
    )

    return updated_order


def start_picking(order):
    """Передаёт полностью оплаченный заказ на комплектование."""
    if order["status"] != STATUS_PAID:
        raise ValueError(
            "Передать заказ на комплектование можно только после полной оплаты."
        )

    updated_order = deepcopy(order)
    updated_order["status"] = STATUS_PICKING

    updated_order["history"].append(
        {
            "action": "Заказ передан на комплектование",
            "status": STATUS_PICKING,
        }
    )

    return updated_order