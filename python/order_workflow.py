from copy import deepcopy
from decimal import Decimal

from inventory import (
    aggregate_order_quantities,
    get_available_quantity,
    reserve_order,
)

from order_calculations import (
    calculate_order_total,
    create_order_item,
    parse_price,
    validate_quantity,
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


STATUS_READY = "Готов к отгрузке"
STATUS_COMPLETED = "Завершён"


def mark_ready_for_shipment(order, picked_quantities):
    """Проверяет комплектность и разрешает отгрузку."""
    if order["status"] != STATUS_PICKING:
        raise ValueError(
            "Проверить комплектность можно только для комплектуемого заказа."
        )

    required_quantities = aggregate_order_quantities(order["items"])

    checked_quantities = {
        sku: validate_quantity(quantity)
        for sku, quantity in picked_quantities.items()
    }

    if checked_quantities != required_quantities:
        raise ValueError(
            "Состав подобранных товаров не совпадает с заказом."
        )

    updated_order = deepcopy(order)
    updated_order["status"] = STATUS_READY

    updated_order["history"].append(
        {
            "action": "Комплектность проверена",
            "status": STATUS_READY,
        }
    )

    return updated_order


def ship_order(order, stock, operation_key):
    """
    Выполняет отгрузку и возвращает новые состояния заказа и склада.

    Повтор с тем же ключом для завершённого заказа
    возвращает сохранённый результат без нового списания.
    """
    if not isinstance(operation_key, str) or not operation_key.strip():
        raise ValueError("Необходимо указать ключ операции отгрузки.")

    operation_key = operation_key.strip()

    if order["status"] == STATUS_COMPLETED:
        previous_shipment = order.get("shipment")

        if (
            previous_shipment is not None
            and previous_shipment["operation_key"] == operation_key
        ):
            return deepcopy(order), deepcopy(stock)

        raise ValueError("Заказ уже отгружен. Новая отгрузка запрещена.")

    if order["status"] != STATUS_READY:
        raise ValueError("Заказ должен быть готов к отгрузке.")

    if get_remaining_amount(order) != Decimal("0.00"):
        raise ValueError("Отгрузка разрешена только после полной оплаты.")

    required_quantities = aggregate_order_quantities(order["items"])

    # Проверяем все позиции до изменения данных.
    for sku, quantity in required_quantities.items():
        if sku not in stock:
            raise ValueError(f"Товар {sku} отсутствует на складе.")

        balance = stock[sku]

        # Одновременно проверяем корректность складских количеств.
        get_available_quantity(balance)

        if balance["on_hand"] < quantity:
            raise ValueError(
                f"Недостаточный физический остаток товара {sku}."
            )

        if balance["reserved"] < quantity:
            raise ValueError(
                f"Недостаточный резерв товара {sku}."
            )

    updated_order = deepcopy(order)
    updated_stock = deepcopy(stock)
    shipment_items = []

    for sku, quantity in required_quantities.items():
        updated_stock[sku]["on_hand"] -= quantity
        updated_stock[sku]["reserved"] -= quantity

        shipment_items.append(
            {
                "sku": sku,
                "quantity": quantity,
            }
        )

    updated_order["shipment"] = {
        "operation_key": operation_key,
        "items": shipment_items,
    }

    updated_order["status"] = STATUS_COMPLETED

    updated_order["history"].append(
        {
            "action": f"Отгрузка выполнена: {operation_key}",
            "status": STATUS_COMPLETED,
        }
    )

    return updated_order, updated_stock


STATUS_CANCELLED = "Отменён"


def cancel_order(order, stock, reason):
    """
    Отменяет заказ до отгрузки.

    Физический запас не изменяется.
    Для подтверждённого заказа освобождается его резерв.
    Зарегистрированные платежи сохраняются.
    """
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Необходимо указать причину отмены.")

    if order["status"] == STATUS_COMPLETED:
        raise ValueError("Отгруженный заказ отменить нельзя.")

    if order["status"] == STATUS_CANCELLED:
        raise ValueError("Заказ уже отменён.")

    allowed_statuses = {
        STATUS_DRAFT,
        STATUS_AWAITING_PAYMENT,
        STATUS_PAID,
        STATUS_PICKING,
        STATUS_READY,
    }

    if order["status"] not in allowed_statuses:
        raise ValueError("Текущее состояние заказа не допускает отмену.")

    # В черновике резерв ещё не создавался.
    has_reservation = order["status"] != STATUS_DRAFT

    required_quantities = {}

    if has_reservation:
        required_quantities = aggregate_order_quantities(order["items"])

        # Проверяем все позиции до освобождения резерва.
        for sku, quantity in required_quantities.items():
            if sku not in stock:
                raise ValueError(f"Товар {sku} отсутствует на складе.")

            balance = stock[sku]
            get_available_quantity(balance)

            if balance["reserved"] < quantity:
                raise ValueError(
                    f"Недостаточный резерв товара {sku} для отмены."
                )

    updated_order = deepcopy(order)
    updated_stock = deepcopy(stock)

    for sku, quantity in required_quantities.items():
        updated_stock[sku]["reserved"] -= quantity

    updated_order["status"] = STATUS_CANCELLED
    updated_order["cancellation_reason"] = reason.strip()

    # Это задача на урегулирование расчётов, а не выполненный возврат.
    updated_order["refund_required"] = (
        get_paid_amount(updated_order) > Decimal("0.00")
    )

    updated_order["history"].append(
        {
            "action": f"Заказ отменён: {reason.strip()}",
            "status": STATUS_CANCELLED,
        }
    )

    return updated_order, updated_stock