package ru.mirea.furniture;

import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Collections;
import java.util.Map;

public final class Main {
    public static void main(String[] args) {
        System.setOut(
                new PrintStream(System.out, true, StandardCharsets.UTF_8)
        );
        System.setErr(
                new PrintStream(System.err, true, StandardCharsets.UTF_8)
        );

        Product table = new Product("ST-01", "Стол офисный", "12500.00");
        Product chair = new Product("KR-01", "Кресло офисное", "8750.00");

        OrderService service = new OrderService(Arrays.asList(
                new StockBalance(table, 10, 2),
                new StockBalance(chair, 20, 5)
        ));

        Order order = service.createOrder(
                "JAVA-001",
                "Учебный покупатель",
                Arrays.asList(
                        new OrderItem(table, 3),
                        new OrderItem(chair, 4)
                )
        );

        System.out.println("ОБЪЕКТНАЯ ОБРАБОТКА ЗАКАЗА");
        System.out.println("Заказ: " + order.getNumber());
        System.out.println("Стоимость: " + order.getTotal() + " руб.");

        service.reserve(order.getNumber());
        System.out.println("После резервирования: " + order.getStatus());
        printStock(service);

        // Сначала проверяется кресло, которого достаточно,
        // затем стол, которого недостаточно.
        Order excessiveOrder = service.createOrder(
                "JAVA-002",
                "Другой покупатель",
                Arrays.asList(
                        new OrderItem(chair, 1),
                        new OrderItem(table, 6)
                )
        );

        try {
            service.reserve(excessiveOrder.getNumber());
            throw new AssertionError("Дефицит ошибочно разрешён.");
        } catch (InsufficientStockException exception) {
            System.out.println("Ожидаемый отказ: " + exception.getMessage());
        }

        checkBalance(service, "ST-01", 10, 5);
        checkBalance(service, "KR-01", 20, 9);

        if (excessiveOrder.getStatus() != OrderStatus.DRAFT) {
            throw new AssertionError("Отклонённый заказ изменил состояние.");
        }

        service.registerPayment("JAVA-001", "PAY-JAVA-001-01", "35000.00");

        try {
            service.startPicking("JAVA-001");
            throw new AssertionError("Частичная оплата разрешила комплектацию.");
        } catch (InvalidOrderStateException exception) {
            System.out.println("Частичная оплата: комплектование запрещено.");
        }

        service.registerPayment("JAVA-001", "PAY-JAVA-001-02", "37500.00");
        service.startPicking("JAVA-001");
        service.markReady("JAVA-001", Map.of("ST-01", 3, "KR-01", 4));

        if (!service.ship("JAVA-001", "SHIP-JAVA-001")) {
            throw new AssertionError("Первая отгрузка не выполнена.");
        }

        if (service.ship("JAVA-001", "SHIP-JAVA-001")) {
            throw new AssertionError("Повторная отгрузка списала товар.");
        }

        checkBalance(service, "ST-01", 7, 2);
        checkBalance(service, "KR-01", 16, 5);

        Order cancelledOrder = service.createOrder(
                "JAVA-003",
                "Покупатель с отменой",
                Collections.singletonList(new OrderItem(chair, 1))
        );

        service.reserve(cancelledOrder.getNumber());
        service.cancel(cancelledOrder.getNumber());

        checkBalance(service, "KR-01", 16, 5);

        System.out.println();
        System.out.println("ИТОГОВОЕ СОСТОЯНИЕ");
        System.out.println("Статус: " + order.getStatus());
        System.out.println("Оплачено: " + order.getPaid());
        System.out.println("Осталось оплатить: " + order.getRemaining());
        printStock(service);

        System.out.println();
        System.out.println("ИСТОРИЯ ЗАКАЗА");
        order.getHistory().forEach(System.out::println);

        System.out.println();
        System.out.println("Проверки объектного сценария пройдены.");
    }

    private static void printStock(OrderService service) {
        for (StockBalance balance : service.getStockSnapshot().values()) {
            System.out.printf(
                    "%s: наличие=%d, резерв=%d, доступно=%d%n",
                    balance.getProduct().getSku(),
                    balance.getOnHand(),
                    balance.getReserved(),
                    balance.getAvailable()
            );
        }
    }

    private static void checkBalance(
            OrderService service, String sku, int onHand, int reserved
    ) {
        StockBalance balance = service.getStockSnapshot().get(sku);

        if (balance == null
                || balance.getOnHand() != onHand
                || balance.getReserved() != reserved) {
            throw new AssertionError("Неверное состояние товара " + sku);
        }
    }
}