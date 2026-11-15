package ru.mirea.furniture;

import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class JdbcOrderService {
    private final TransactionManager transactions;
    private final OrderRepository repository;
    private final JdbcAuthenticationService authentication;

    public JdbcOrderService(
            TransactionManager transactions,
            OrderRepository repository,
            JdbcAuthenticationService authentication
    ) {
        this.transactions = transactions;
        this.repository = repository;
        this.authentication = authentication;
    }

    public long createDraft(
            Order draft,
            String customerInn,
            String warehouseName,
            String login,
            char[] password
    ) throws SQLException {
        if (draft.getStatus() != OrderStatus.DRAFT) {
            throw new InvalidOrderStateException("Требуется черновик.");
        }

        if (draft.getNumber().length() > 40) {
            throw new BusinessException("Слишком длинный номер заказа.");
        }

        Order normalized = normalizeOrder(draft);

        return transactions.execute(connection -> {
            long userId = authentication.authenticate(
                    connection, login, password
            );
            authentication.requireRole(connection, userId, "manager");

            return repository.createDraft(
                    connection, normalized,
                    customerInn, warehouseName, userId
            );
        });
    }

    public boolean reserve(
            String number,
            String operationKey,
            String login,
            char[] password
    ) throws SQLException {
        if (operationKey == null || operationKey.isBlank()
                || operationKey.strip().length() > 64) {
            throw new BusinessException("Некорректный ключ резервирования.");
        }

        final String key = operationKey.strip();

        return transactions.execute(connection -> {
            long userId = authentication.authenticate(
                    connection, login, password
            );
            authentication.requireRole(connection, userId, "manager");

            OrderRepository.LockedOrder order =
                    repository.lockOrder(connection, number);

            if (order.managerId != userId) {
                throw new BusinessException(
                        "Заказ закреплён за другим менеджером."
                );
            }

            if ("awaiting_payment".equals(order.status)
                    && Objects.equals(order.reserveKey, key)) {
                return false;
            }

            if (!"draft".equals(order.status)) {
                throw new InvalidOrderStateException(
                        "Резервировать можно только черновик."
                );
            }

            List<OrderRepository.StockLine> lines =
                    repository.lockStock(connection, order);

            if (lines.isEmpty()) {
                throw new BusinessException("Заказ не содержит товаров.");
            }

            for (OrderRepository.StockLine line : lines) {
                if (line.quantity > line.onHand - line.reserved) {
                    throw new InsufficientStockException(
                            "Недостаточно товара " + line.sku
                    );
                }
            }

            repository.saveReservation(
                    connection, order, lines, key, userId
            );

            return true;
        });
    }

    private Order normalizeOrder(Order source) {
        Map<String, OrderItem> merged = new LinkedHashMap<>();

        for (OrderItem item : source.getItems()) {
            String sku = item.getProduct().getSku();
            OrderItem previous = merged.get(sku);

            if (previous == null) {
                merged.put(sku, item);
                continue;
            }

            if (previous.getUnitPrice().compareTo(item.getUnitPrice()) != 0) {
                throw new BusinessException(
                        "Разные цены повторяющегося товара " + sku
                );
            }

            int quantity;

            try {
                quantity = Math.addExact(
                        previous.getQuantity(), item.getQuantity()
                );
            } catch (ArithmeticException exception) {
                throw new BusinessException("Слишком большое количество.");
            }

            merged.put(
                    sku,
                    new OrderItem(previous.getProduct(), quantity)
            );
        }

        return new Order(
                source.getNumber(),
                source.getCustomer(),
                new ArrayList<>(merged.values())
        );
    }
}