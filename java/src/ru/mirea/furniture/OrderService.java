package ru.mirea.furniture;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class OrderService {
    private final Map<String, Order> orders = new LinkedHashMap<>();
    private Map<String, StockBalance> stock = new LinkedHashMap<>();

    public OrderService(List<StockBalance> initialBalances) {
        for (StockBalance balance : initialBalances) {
            String sku = balance.getProduct().getSku();

            if (stock.containsKey(sku)) {
                throw new BusinessException("Повторный остаток товара " + sku);
            }

            stock.put(sku, balance.copy());
        }
    }

    public synchronized Order createOrder(
            String number,
            String customer,
            List<OrderItem> items
    ) {
        Order order = new Order(number, customer, items);

        if (orders.containsKey(order.getNumber())) {
            throw new BusinessException("Номер заказа уже существует.");
        }

        orders.put(order.getNumber(), order);
        return order;
    }

    public synchronized void reserve(String number) {
        Order order = getOrder(number);
        requireStatus(order, OrderStatus.DRAFT);

        changeStock(order, "reserve");

        order.changeStatus(
                OrderStatus.AWAITING_PAYMENT,
                "Товары зарезервированы"
        );
    }

    public synchronized void registerPayment(
            String number, String reference, String amount
    ) {
        Order order = getOrder(number);
        requireStatus(order, OrderStatus.AWAITING_PAYMENT);
        order.recordPayment(reference, amount);
    }

    public synchronized void startPicking(String number) {
        Order order = getOrder(number);
        requireStatus(order, OrderStatus.PAID);

        order.changeStatus(
                OrderStatus.PICKING,
                "Передан на комплектование"
        );
    }

    public synchronized void markReady(
            String number, Map<String, Integer> pickedQuantities
    ) {
        Order order = getOrder(number);
        requireStatus(order, OrderStatus.PICKING);

        if (!requiredQuantities(order).equals(pickedQuantities)) {
            throw new BusinessException(
                    "Подобранное количество не совпадает с заказом."
            );
        }

        order.changeStatus(
                OrderStatus.READY,
                "Комплектность проверена"
        );
    }

    public synchronized boolean ship(String number, String operationKey) {
        Order order = getOrder(number);

        if (operationKey == null || operationKey.isBlank()) {
            throw new BusinessException("Не указан ключ отгрузки.");
        }

        operationKey = operationKey.strip();

        if (order.getStatus() == OrderStatus.COMPLETED) {
            if (Objects.equals(order.getShipmentKey(), operationKey)) {
                return false;
            }

            throw new InvalidOrderStateException(
                    "Заказ уже отгружен с другим ключом."
            );
        }

        requireStatus(order, OrderStatus.READY);

        if (order.getRemaining().signum() != 0) {
            throw new BusinessException("Заказ оплачен не полностью.");
        }

        changeStock(order, "ship");
        order.setShipmentKey(operationKey);
        order.changeStatus(OrderStatus.COMPLETED, "Отгрузка выполнена");

        return true;
    }

    public synchronized void cancel(String number) {
        Order order = getOrder(number);

        if (order.getStatus() == OrderStatus.COMPLETED
                || order.getStatus() == OrderStatus.CANCELLED) {
            throw new InvalidOrderStateException(
                    "Отмена в текущем состоянии запрещена."
            );
        }

        if (order.getStatus() != OrderStatus.DRAFT) {
            changeStock(order, "release");
        }

        order.changeStatus(OrderStatus.CANCELLED, "Заказ отменён");
    }

    public synchronized Map<String, StockBalance> getStockSnapshot() {
        return Collections.unmodifiableMap(copyStock());
    }

    private Order getOrder(String number) {
        Order order = orders.get(number);

        if (order == null) {
            throw new BusinessException("Заказ не найден.");
        }

        return order;
    }

    private void requireStatus(Order order, OrderStatus expected) {
        if (order.getStatus() != expected) {
            throw new InvalidOrderStateException(
                    "Требуется состояние «" + expected
                    + "», текущее — «" + order.getStatus() + "»."
            );
        }
    }

    private Map<String, Integer> requiredQuantities(Order order) {
        Map<String, Integer> quantities = new LinkedHashMap<>();

        for (OrderItem item : order.getItems()) {
            String sku = item.getProduct().getSku();

            try {
                quantities.merge(sku, item.getQuantity(), Math::addExact);
            } catch (ArithmeticException exception) {
                throw new BusinessException(
                        "Слишком большое количество товара " + sku
                );
            }
        }

        return quantities;
    }

    private Map<String, StockBalance> copyStock() {
        Map<String, StockBalance> copy = new LinkedHashMap<>();

        for (Map.Entry<String, StockBalance> entry : stock.entrySet()) {
            copy.put(entry.getKey(), entry.getValue().copy());
        }

        return copy;
    }

    private void changeStock(Order order, String operation) {
        // Меняем независимую копию. Общий склад заменяем
        // только после успешной обработки всех товаров.
        Map<String, StockBalance> updated = copyStock();

        for (Map.Entry<String, Integer> entry
                : requiredQuantities(order).entrySet()) {
            StockBalance balance = updated.get(entry.getKey());
            int quantity = entry.getValue();

            if (balance == null) {
                throw new InsufficientStockException(
                        "Товар не найден: " + entry.getKey()
                );
            }

            if ("reserve".equals(operation)) {
                if (quantity > balance.getAvailable()) {
                    throw new InsufficientStockException(
                            "Недостаточно товара " + entry.getKey()
                    );
                }

                balance.reserve(quantity);
            } else if ("release".equals(operation)) {
                balance.release(quantity);
            } else if ("ship".equals(operation)) {
                balance.ship(quantity);
            } else {
                throw new BusinessException("Неизвестная операция склада.");
            }
        }

        stock = updated;
    }
}