package ru.mirea.furniture;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class Order {
    private final String number;
    private final String customer;
    private final List<OrderItem> items;
    private final BigDecimal total;
    private final Map<String, BigDecimal> payments = new LinkedHashMap<>();
    private final List<String> history = new ArrayList<>();

    private OrderStatus status = OrderStatus.DRAFT;
    private String shipmentKey;

    public Order(String number, String customer, List<OrderItem> items) {
        if (number == null || number.isBlank()
                || customer == null || customer.isBlank()) {
            throw new BusinessException("Не указан номер или покупатель.");
        }

        if (items == null || items.isEmpty()
                || items.stream().anyMatch(Objects::isNull)) {
            throw new BusinessException("Необходимо указать строки заказа.");
        }

        this.number = number.strip();
        this.customer = customer.strip();
        this.items = Collections.unmodifiableList(new ArrayList<>(items));
        this.total = items.stream()
                .map(OrderItem::getTotal)
                .reduce(new BigDecimal("0.00"), BigDecimal::add);

        if (total.compareTo(new BigDecimal("999999999999.99")) > 0) {
            throw new BusinessException("Сумма заказа слишком велика.");
        }

        history.add("Создан заказ: " + status);
    }

    public String getNumber() {
        return number;
    }

    public String getCustomer() {
        return customer;
    }

    public List<OrderItem> getItems() {
        return items;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public BigDecimal getPaid() {
        return payments.values().stream()
                .reduce(new BigDecimal("0.00"), BigDecimal::add);
    }

    public BigDecimal getRemaining() {
        return total.subtract(getPaid());
    }

    public OrderStatus getStatus() {
        return status;
    }

    public String getShipmentKey() {
        return shipmentKey;
    }

    public List<String> getHistory() {
        return Collections.unmodifiableList(new ArrayList<>(history));
    }

    void changeStatus(OrderStatus newStatus, String reason) {
        status = newStatus;
        history.add(reason + " → " + newStatus);
    }

    void setShipmentKey(String key) {
        shipmentKey = key;
    }

    void recordPayment(String reference, String amount) {
        if (reference == null || reference.isBlank()) {
            throw new BusinessException("Не указан номер платежа.");
        }

        reference = reference.strip();

        if (payments.containsKey(reference)) {
            throw new BusinessException("Платёж уже зарегистрирован.");
        }

        BigDecimal value;

        try {
            if (amount == null) {
                throw new NumberFormatException();
            }

            value = new BigDecimal(amount)
                    .setScale(2, RoundingMode.UNNECESSARY);
        } catch (NumberFormatException | ArithmeticException exception) {
            throw new BusinessException("Некорректная сумма платежа.");
        }

        if (value.signum() <= 0 || value.compareTo(getRemaining()) > 0) {
            throw new BusinessException(
                    "Сумма платежа должна быть положительной "
                    + "и не превышать остаток к оплате."
            );
        }

        payments.put(reference, value);
        history.add("Зарегистрирован платёж " + reference);

        if (getRemaining().signum() == 0) {
            changeStatus(OrderStatus.PAID, "Полная оплата");
        }
    }
}