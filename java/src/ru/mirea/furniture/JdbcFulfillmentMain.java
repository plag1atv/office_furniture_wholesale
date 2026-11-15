package ru.mirea.furniture;

import java.io.Console;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.sql.SQLException;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public final class JdbcFulfillmentMain {
    public static void main(String[] args) {
        System.setOut(
                new PrintStream(System.out, true, StandardCharsets.UTF_8)
        );
        System.setErr(
                new PrintStream(System.err, true, StandardCharsets.UTF_8)
        );

        char[] accountantPassword = null;
        char[] warehousePassword = null;

        try {
            Console console = System.console();

            if (console == null) {
                throw new BusinessException("Запускай программу из терминала.");
            }

            String number = args.length > 0
                    ? args[0] : "JAVA-DB-844d88cf";

            accountantPassword = console.readPassword(
                    "Password accountant: "
            );
            warehousePassword = console.readPassword(
                    "Password warehouse: "
            );

            JdbcFulfillmentService service = new JdbcFulfillmentService(
                    new JdbcTransactionManager(
                            new DatabaseConnectionFactory()
                    ),
                    new JdbcOrderRepository(),
                    new JdbcAuthenticationService()
            );

            String firstPayment = "PAY-" + number + "-01";
            String secondPayment = "PAY-" + number + "-02";
            String shipmentKey = "SHIP-" + number;

            JdbcFulfillmentService.PaymentResult partial = service.pay(
                    number, firstPayment, "35000.00",
                    "accountant", accountantPassword
            );
            printPayment("ПЕРВЫЙ ПЛАТЁЖ", partial);

            JdbcFulfillmentService.PaymentResult repeatPayment = service.pay(
                    number, firstPayment, "35000.00",
                    "accountant", accountantPassword
            );

            if (!repeatPayment.repeated) {
                throw new AssertionError("Повтор платежа не распознан.");
            }

            System.out.println("Повтор первого платежа: дубликат не создан.");

            if (partial.total.compareTo(partial.paid) > 0) {
                try {
                    service.prepare(
                            number, Map.of("ST-01", 3, "KR-01", 4),
                            "warehouse", warehousePassword
                    );
                    throw new AssertionError(
                            "Частичная оплата разрешила комплектование."
                    );
                } catch (InvalidOrderStateException exception) {
                    System.out.println(
                            "Частичная оплата: комплектование запрещено."
                    );
                }
            }

            JdbcFulfillmentService.PaymentResult full = service.pay(
                    number, secondPayment, "37500.00",
                    "accountant", accountantPassword
            );
            printPayment("ПОЛНАЯ ОПЛАТА", full);

            service.prepare(
                    number, Map.of("ST-01", 3, "KR-01", 4),
                    "warehouse", warehousePassword
            );

            JdbcFulfillmentService.ShipmentResult shipment = service.ship(
                    number, shipmentKey,
                    "warehouse", warehousePassword
            );

            JdbcFulfillmentService.ShipmentResult repeatedShipment =
                    service.ship(
                            number, shipmentKey,
                            "warehouse", warehousePassword
                    );

            if (!repeatedShipment.repeated
                    || repeatedShipment.shipmentId != shipment.shipmentId
                    || !signature(shipment.after).equals(
                            signature(repeatedShipment.after)
                    )) {
                throw new AssertionError(
                        "Повторная отгрузка изменила результат."
                );
            }

            System.out.println();
            System.out.println("ИТОГ ОБРАБОТКИ ЗАКАЗА JAVA / POSTGRESQL");
            System.out.println("Заказ: " + number);
            System.out.println("Стоимость: " + full.total);
            System.out.println("Оплачено: " + full.paid);
            System.out.println(
                    "Осталось оплатить: " + full.total.subtract(full.paid)
            );
            System.out.println("Статус: completed — Завершён");
            System.out.println("Отгрузка: " + shipment.shipmentId);

            if (!shipment.repeated) {
                printStock("ДО ОТГРУЗКИ", shipment.before);
            }

            printStock("ПОСЛЕ ОТГРУЗКИ", shipment.after);

            System.out.println();
            System.out.println(
                    "Повторная отгрузка не создала новых списаний."
            );

        } catch (SQLException | BusinessException exception) {
            System.err.println("Ошибка: " + exception.getMessage());
            System.exit(1);
        } finally {
            if (accountantPassword != null) {
                Arrays.fill(accountantPassword, '\0');
            }
            if (warehousePassword != null) {
                Arrays.fill(warehousePassword, '\0');
            }
        }
    }

    private static void printPayment(
            String title, JdbcFulfillmentService.PaymentResult result
    ) {
        System.out.println();
        System.out.println(title);
        System.out.println("Статус: " + result.status);
        System.out.println("Оплачено: " + result.paid);
        System.out.println(
                "Осталось: " + result.total.subtract(result.paid)
        );
    }

    private static void printStock(
            String title, List<OrderRepository.StockLine> rows
    ) {
        System.out.println();
        System.out.println(title);

        for (OrderRepository.StockLine row : rows) {
            System.out.printf(
                    "%s: наличие=%d, резерв=%d, доступно=%d%n",
                    row.sku, row.onHand, row.reserved,
                    row.onHand - row.reserved
            );
        }
    }

    private static String signature(List<OrderRepository.StockLine> rows) {
        return rows.stream()
                .map(row -> row.sku + ":" + row.onHand + ":" + row.reserved)
                .sorted()
                .collect(Collectors.joining("|"));
    }
}