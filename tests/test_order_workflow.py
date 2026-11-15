import sys
import unittest
from copy import deepcopy
from decimal import Decimal
from pathlib import Path


# Добавляем папку с реализацией в путь поиска модулей.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "python"))

from inventory import aggregate_order_quantities, reserve_order
from order_calculations import (
    calculate_order_total,
    create_order_item,
)
from order_workflow import (
    STATUS_AWAITING_PAYMENT,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_PAID,
    STATUS_PICKING,
    cancel_order,
    confirm_order,
    create_order,
    get_paid_amount,
    get_remaining_amount,
    mark_ready_for_shipment,
    register_payment,
    ship_order,
    start_picking,
)


class OrderWorkflowTests(unittest.TestCase):
    def setUp(self):
        """Перед каждым тестом создаёт независимые исходные данные."""
        self.stock = {
            "ST-01": {"on_hand": 10, "reserved": 2},
            "KR-01": {"on_hand": 20, "reserved": 5},
        }

        self.items = [
            create_order_item(
                "ST-01", "Стол офисный", 3, "12500.00"
            ),
            create_order_item(
                "KR-01", "Кресло офисное", 4, "8750.00"
            ),
        ]

        self.order = create_order(
            "TEST-001",
            "Учебный покупатель",
            self.items,
        )

    def prepare_confirmed_order(self):
        """Возвращает заказ с созданным резервом."""
        return confirm_order(self.order, self.stock)

    def prepare_ready_order(self):
        """Возвращает полностью оплаченный и собранный заказ."""
        order, stock = self.prepare_confirmed_order()

        order = register_payment(
            order, "72500.00", "PAY-TEST-001"
        )

        order = start_picking(order)

        order = mark_ready_for_shipment(
            order,
            {"ST-01": 3, "KR-01": 4},
        )

        return order, stock

    def test_01_order_total(self):
        total = calculate_order_total(self.items)

        self.assertEqual(total, Decimal("72500.00"))

    def test_02_invalid_quantities(self):
        for quantity in (0, -1, True, 1.5):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValueError):
                    create_order_item(
                        "ST-01",
                        "Стол офисный",
                        quantity,
                        "12500.00",
                    )

    def test_03_repeated_products_are_aggregated(self):
        items = [
            create_order_item("ST-01", "Стол", 3, "12500.00"),
            create_order_item("ST-01", "Стол", 2, "12500.00"),
        ]

        quantities = aggregate_order_quantities(items)

        self.assertEqual(quantities, {"ST-01": 5})

    def test_04_successful_reservation(self):
        original_stock = deepcopy(self.stock)

        order, stock = self.prepare_confirmed_order()

        self.assertEqual(order["status"], STATUS_AWAITING_PAYMENT)
        self.assertEqual(
            stock["ST-01"],
            {"on_hand": 10, "reserved": 5},
        )
        self.assertEqual(
            stock["KR-01"],
            {"on_hand": 20, "reserved": 9},
        )

        # Функция возвращает новое состояние, исходное не меняет.
        self.assertEqual(self.stock, original_stock)

    def test_05_shortage_does_not_create_partial_reservation(self):
        items = [
            create_order_item("KR-01", "Кресло", 1, "8750.00"),
            create_order_item("ST-01", "Стол", 9, "12500.00"),
        ]

        original_stock = deepcopy(self.stock)

        with self.assertRaises(ValueError):
            reserve_order(items, self.stock)

        self.assertEqual(self.stock, original_stock)

    def test_06_partial_payment_blocks_picking(self):
        order, stock = self.prepare_confirmed_order()
        order = register_payment(order, "35000.00", "PAY-001")

        self.assertEqual(order["status"], STATUS_AWAITING_PAYMENT)
        self.assertEqual(get_paid_amount(order), Decimal("35000.00"))
        self.assertEqual(
            get_remaining_amount(order),
            Decimal("37500.00"),
        )

        with self.assertRaises(ValueError):
            start_picking(order)

    def test_07_duplicate_payment_is_rejected(self):
        order, stock = self.prepare_confirmed_order()
        order = register_payment(order, "35000.00", "PAY-001")

        original_order = deepcopy(order)

        with self.assertRaises(ValueError):
            register_payment(order, "35000.00", "PAY-001")

        self.assertEqual(order, original_order)
        self.assertEqual(len(order["payments"]), 1)

    def test_08_overpayment_is_rejected(self):
        order, stock = self.prepare_confirmed_order()
        original_order = deepcopy(order)

        with self.assertRaises(ValueError):
            register_payment(order, "72500.01", "PAY-001")

        self.assertEqual(order, original_order)

    def test_09_incomplete_picking_is_rejected(self):
        order, stock = self.prepare_confirmed_order()
        order = register_payment(order, "72500.00", "PAY-001")

        self.assertEqual(order["status"], STATUS_PAID)

        order = start_picking(order)

        with self.assertRaises(ValueError):
            mark_ready_for_shipment(
                order,
                {"ST-01": 2, "KR-01": 4},
            )

        self.assertEqual(order["status"], STATUS_PICKING)

    def test_10_shipment_updates_stock(self):
        order, stock = self.prepare_ready_order()

        order, stock = ship_order(order, stock, "SHIP-001")

        self.assertEqual(order["status"], STATUS_COMPLETED)
        self.assertEqual(
            stock["ST-01"],
            {"on_hand": 7, "reserved": 2},
        )
        self.assertEqual(
            stock["KR-01"],
            {"on_hand": 16, "reserved": 5},
        )

    def test_11_repeated_shipment_does_not_write_off_twice(self):
        order, stock = self.prepare_ready_order()
        order, stock = ship_order(order, stock, "SHIP-001")

        original_order = deepcopy(order)
        original_stock = deepcopy(stock)

        repeated_order, repeated_stock = ship_order(
            order, stock, "SHIP-001"
        )

        self.assertEqual(repeated_order, original_order)
        self.assertEqual(repeated_stock, original_stock)

        with self.assertRaises(ValueError):
            ship_order(order, stock, "SHIP-002")

        self.assertEqual(order, original_order)
        self.assertEqual(stock, original_stock)

    def test_12_cancellation_releases_reservation_and_keeps_payment(self):
        order, stock = self.prepare_confirmed_order()
        order = register_payment(order, "35000.00", "PAY-001")

        order, stock = cancel_order(
            order, stock, "Отказ покупателя"
        )

        self.assertEqual(order["status"], STATUS_CANCELLED)
        self.assertEqual(stock, self.stock)
        self.assertEqual(get_paid_amount(order), Decimal("35000.00"))
        self.assertTrue(order["refund_required"])

        cancelled_order = deepcopy(order)
        cancelled_stock = deepcopy(stock)

        with self.assertRaises(ValueError):
            cancel_order(order, stock, "Повторная отмена")

        self.assertEqual(order, cancelled_order)
        self.assertEqual(stock, cancelled_stock)

    def test_13_draft_cancellation_does_not_release_other_reservations(self):
        order, stock = cancel_order(
            self.order,
            self.stock,
            "Отмена черновика",
        )

        self.assertEqual(order["status"], STATUS_CANCELLED)
        self.assertEqual(stock, self.stock)
        self.assertFalse(order["refund_required"])

    def test_14_completed_order_cannot_be_cancelled(self):
        order, stock = self.prepare_ready_order()
        order, stock = ship_order(order, stock, "SHIP-001")

        original_order = deepcopy(order)
        original_stock = deepcopy(stock)

        with self.assertRaises(ValueError):
            cancel_order(order, stock, "Попытка отмены после отгрузки")

        self.assertEqual(order, original_order)
        self.assertEqual(stock, original_stock)


if __name__ == "__main__":
    unittest.main(verbosity=2)