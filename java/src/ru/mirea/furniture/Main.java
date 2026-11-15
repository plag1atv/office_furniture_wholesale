package ru.mirea.furniture;

import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

public final class Main {
    public static void main(String[] args) {
        System.setOut(
                new PrintStream(System.out, true, StandardCharsets.UTF_8)
        );
        System.setErr(
                new PrintStream(System.err, true, StandardCharsets.UTF_8)
        );

        Product table = new Product(
                "ST-01", "Стол офисный", "12500.00"
        );

        Product chair = new Product(
                "KR-01", "Кресло офисное", "8750.00"
        );

        List<OrderItem> items = Arrays.asList(
                new OrderItem(table, 3),
                new OrderItem(chair, 4)
        );

        System.out.println("ОБЪЕКТНАЯ МОДЕЛЬ НА JAVA");
        System.out.println();
        System.out.println("СОСТАВ ЗАКАЗА");

        BigDecimal total = new BigDecimal("0.00");

        for (OrderItem item : items) {
            System.out.printf(
                    "%s | %s | %d шт. | %s руб.%n",
                    item.getProduct().getSku(),
                    item.getProduct().getName(),
                    item.getQuantity(),
                    item.getTotal().toPlainString()
            );

            total = total.add(item.getTotal());
        }

        System.out.println("ИТОГО: " + total.toPlainString() + " руб.");

        if (total.compareTo(new BigDecimal("72500.00")) != 0) {
            throw new IllegalStateException("Неверная сумма заказа.");
        }

        StockBalance balance = new StockBalance(table, 10, 2);

        System.out.println();
        System.out.println("ПРОВЕРКА ОБЪЕКТА СКЛАДСКОГО ОСТАТКА");

        printBalance(balance);

        balance.reserve(3);

        System.out.println("После резервирования 3 столов:");
        printBalance(balance);

        try {
            balance.reserve(6);
            throw new AssertionError("Дефицит ошибочно разрешён.");
        } catch (IllegalStateException exception) {
            System.out.println(
                    "Ожидаемый отказ: " + exception.getMessage()
            );
        }

        if (balance.getOnHand() != 10
                || balance.getReserved() != 5
                || balance.getAvailable() != 5) {
            throw new IllegalStateException(
                    "После отказа складское состояние нарушено."
            );
        }

        System.out.println();
        System.out.println("Проверки модели пройдены.");
    }

    private static void printBalance(StockBalance balance) {
        System.out.printf(
                "%s: наличие=%d, резерв=%d, доступно=%d%n",
                balance.getProduct().getSku(),
                balance.getOnHand(),
                balance.getReserved(),
                balance.getAvailable()
        );
    }
}