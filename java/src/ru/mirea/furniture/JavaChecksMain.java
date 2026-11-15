package ru.mirea.furniture;

import java.io.PrintStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Collections;
import java.util.Map;

public final class JavaChecksMain {
    private static int passed;
    private static int failed;

    public static void main(String[] args) {
        System.setOut(
                new PrintStream(System.out, true, StandardCharsets.UTF_8)
        );
        System.setErr(
                new PrintStream(System.err, true, StandardCharsets.UTF_8)
        );

        System.out.println("АВТОМАТИЧЕСКИЕ ПРОВЕРКИ ОБЪЕКТНОЙ МОДЕЛИ JAVA");

        test("01 Расчёт стоимости", () -> {
            Fixture f = new Fixture();
            money(f.order.getTotal(), "72500.00");
        });

        test("02 Недопустимые количества", () -> {
            Fixture f = new Fixture();

            for (int quantity : new int[]{0, -1}) {
                expect(
                        IllegalArgumentException.class,
                        () -> new OrderItem(f.table, quantity)
                );
            }
        });

        test("03 Объединение повторяющихся артикулов", () -> {
            Fixture f = new Fixture();

            f.service.createOrder(
                    "DUPLICATES",
                    "Покупатель",
                    Arrays.asList(
                            new OrderItem(f.table, 3),
                            new OrderItem(f.table, 2)
                    )
            );

            f.service.reserve("DUPLICATES");
            balance(f, "ST-01", 10, 7);
        });

        test("04 Успешное резервирование", () -> {
            Fixture f = reserved();

            check(
                    f.order.getStatus() == OrderStatus.AWAITING_PAYMENT,
                    "Неверный статус"
            );
            balance(f, "ST-01", 10, 5);
            balance(f, "KR-01", 20, 9);
        });

        test("05 Отсутствие частичного резерва при дефиците", () -> {
            Fixture f = new Fixture();

            Order excessive = f.service.createOrder(
                    "SHORTAGE",
                    "Покупатель",
                    Arrays.asList(
                            new OrderItem(f.chair, 1),
                            new OrderItem(f.table, 9)
                    )
            );

            expect(
                    InsufficientStockException.class,
                    () -> f.service.reserve("SHORTAGE")
            );

            balance(f, "ST-01", 10, 2);
            balance(f, "KR-01", 20, 5);
            check(
                    excessive.getStatus() == OrderStatus.DRAFT,
                    "Заказ изменил состояние"
            );
        });

        test("06 Частичная оплата запрещает комплектование", () -> {
            Fixture f = reserved();
            f.service.registerPayment("TEST", "PAY-1", "35000.00");

            money(f.order.getPaid(), "35000.00");
            money(f.order.getRemaining(), "37500.00");

            expect(
                    InvalidOrderStateException.class,
                    () -> f.service.startPicking("TEST")
            );
        });

        test("07 Повторный платёж отклоняется", () -> {
            Fixture f = reserved();
            f.service.registerPayment("TEST", "PAY-1", "35000.00");

            expect(
                    BusinessException.class,
                    () -> f.service.registerPayment(
                            "TEST", "PAY-1", "35000.00"
                    )
            );

            money(f.order.getPaid(), "35000.00");
        });

        test("08 Переплата отклоняется", () -> {
            Fixture f = reserved();

            expect(
                    BusinessException.class,
                    () -> f.service.registerPayment(
                            "TEST", "PAY-1", "72500.01"
                    )
            );

            money(f.order.getPaid(), "0.00");
        });

        test("09 Неполная комплектация отклоняется", () -> {
            Fixture f = reserved();
            f.service.registerPayment("TEST", "PAY-1", "72500.00");
            f.service.startPicking("TEST");

            expect(
                    BusinessException.class,
                    () -> f.service.markReady(
                            "TEST", Map.of("ST-01", 2, "KR-01", 4)
                    )
            );

            check(
                    f.order.getStatus() == OrderStatus.PICKING,
                    "Неверный статус после отказа"
            );
        });

        test("10 Отгрузка изменяет запас и резерв", () -> {
            Fixture f = ready();

            check(
                    f.service.ship("TEST", "SHIP-1"),
                    "Первая отгрузка не выполнена"
            );

            balance(f, "ST-01", 7, 2);
            balance(f, "KR-01", 16, 5);
            check(
                    f.order.getStatus() == OrderStatus.COMPLETED,
                    "Заказ не завершён"
            );
        });

        test("11 Повторная отгрузка не списывает товар", () -> {
            Fixture f = ready();
            f.service.ship("TEST", "SHIP-1");

            check(
                    !f.service.ship("TEST", "SHIP-1"),
                    "Повтор создал отгрузку"
            );

            expect(
                    InvalidOrderStateException.class,
                    () -> f.service.ship("TEST", "SHIP-2")
            );

            balance(f, "ST-01", 7, 2);
            balance(f, "KR-01", 16, 5);
        });

        test("12 Отмена освобождает резерв и сохраняет оплату", () -> {
            Fixture f = reserved();
            f.service.registerPayment("TEST", "PAY-1", "35000.00");
            f.service.cancel("TEST");

            check(
                    f.order.getStatus() == OrderStatus.CANCELLED,
                    "Заказ не отменён"
            );
            money(f.order.getPaid(), "35000.00");
            balance(f, "ST-01", 10, 2);
            balance(f, "KR-01", 20, 5);

            expect(
                    InvalidOrderStateException.class,
                    () -> f.service.cancel("TEST")
            );
        });

        test("13 Отмена черновика сохраняет чужие резервы", () -> {
            Fixture f = new Fixture();
            f.service.cancel("TEST");

            balance(f, "ST-01", 10, 2);
            balance(f, "KR-01", 20, 5);
        });

        test("14 Отмена завершённого заказа запрещена", () -> {
            Fixture f = ready();
            f.service.ship("TEST", "SHIP-1");
            int historySize = f.order.getHistory().size();

            expect(
                    InvalidOrderStateException.class,
                    () -> f.service.cancel("TEST")
            );

            balance(f, "ST-01", 7, 2);
            balance(f, "KR-01", 16, 5);

            check(
                    f.order.getStatus() == OrderStatus.COMPLETED
                            && f.order.getHistory().size() == historySize,
                    "Завершённый заказ изменился"
            );
        });

        System.out.println();
        System.out.printf(
                "JAVA: выполнено=%d, успешно=%d, ошибок=%d%n",
                passed + failed, passed, failed
        );

        if (failed > 0) {
            System.exit(1);
        }
    }

    private static void test(String name, Runnable action) {
        try {
            action.run();
            passed++;
            System.out.println("[OK] " + name);
        } catch (RuntimeException | AssertionError failure) {
            failed++;
            System.out.println("[FAIL] " + name + ": " + failure.getMessage());
        }
    }

    private static void expect(
            Class<? extends RuntimeException> expected,
            Runnable action
    ) {
        try {
            action.run();
        } catch (RuntimeException failure) {
            if (expected.isInstance(failure)) {
                return;
            }

            throw new AssertionError(
                    "Получен другой тип исключения", failure
            );
        }

        throw new AssertionError("Ожидаемое исключение отсутствует.");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void money(BigDecimal actual, String expected) {
        check(
                actual.compareTo(new BigDecimal(expected)) == 0,
                "Неверная денежная сумма: " + actual
        );
    }

    private static void balance(
            Fixture f, String sku, int onHand, int reserved
    ) {
        StockBalance balance = f.service.getStockSnapshot().get(sku);

        check(
                balance != null
                        && balance.getOnHand() == onHand
                        && balance.getReserved() == reserved
                        && balance.getAvailable() == onHand - reserved,
                "Неверный остаток " + sku
        );
    }

    private static Fixture reserved() {
        Fixture f = new Fixture();
        f.service.reserve("TEST");
        return f;
    }

    private static Fixture ready() {
        Fixture f = reserved();
        f.service.registerPayment("TEST", "PAY-1", "72500.00");
        f.service.startPicking("TEST");
        f.service.markReady("TEST", Map.of("ST-01", 3, "KR-01", 4));
        return f;
    }

    private static final class Fixture {
        private final Product table =
                new Product("ST-01", "Стол офисный", "12500.00");
        private final Product chair =
                new Product("KR-01", "Кресло офисное", "8750.00");

        private final OrderService service = new OrderService(
                Arrays.asList(
                        new StockBalance(table, 10, 2),
                        new StockBalance(chair, 20, 5)
                )
        );

        private final Order order = service.createOrder(
                "TEST",
                "Учебный покупатель",
                Arrays.asList(
                        new OrderItem(table, 3),
                        new OrderItem(chair, 4)
                )
        );
    }
}