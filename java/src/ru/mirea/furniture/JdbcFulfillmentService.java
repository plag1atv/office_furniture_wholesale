package ru.mirea.furniture;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.AbstractMap;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import static ru.mirea.furniture.JdbcSql.*;

public final class JdbcFulfillmentService {
    private final TransactionManager transactions;
    private final OrderRepository repository;
    private final JdbcAuthenticationService authentication;

    public JdbcFulfillmentService(
            TransactionManager transactions,
            OrderRepository repository,
            JdbcAuthenticationService authentication
    ) {
        this.transactions = transactions;
        this.repository = repository;
        this.authentication = authentication;
    }

    public PaymentResult pay(
            String number, String reference, String amount,
            String login, char[] password
    ) throws SQLException {
        BigDecimal value = parseAmount(amount);

        if (reference == null || reference.isBlank()
                || reference.strip().length() > 100) {
            throw new BusinessException("Некорректный номер платежа.");
        }

        final String paymentReference = reference.strip();

        return transactions.execute(connection -> {
            long actor = authenticate(
                    connection, login, password, "accountant"
            );

            OrderRepository.LockedOrder order =
                    repository.lockOrder(connection, number);

            Map.Entry<Long, BigDecimal> existing = one(
                    connection,
                    "SELECT order_id, amount FROM public.payments "
                            + "WHERE external_ref = ?",
                    result -> new AbstractMap.SimpleImmutableEntry<>(
                            result.getLong("order_id"),
                            result.getBigDecimal("amount")
                    ),
                    paymentReference
            );

            BigDecimal total = total(connection, order.id);
            BigDecimal paid = paid(connection, order.id);

            if (existing != null) {
                if (existing.getKey() != order.id
                        || existing.getValue().compareTo(value) != 0) {
                    throw new BusinessException(
                            "Номер платежа занят другим заказом или суммой."
                    );
                }

                return new PaymentResult(
                        order.status, total, paid, true
                );
            }

            if (!"awaiting_payment".equals(order.status)) {
                throw new InvalidOrderStateException(
                        "Заказ не ожидает оплаты."
                );
            }

            long invalidReservations = one(
                    connection,
                    "SELECT count(*) FROM public.order_items AS oi "
                            + "LEFT JOIN public.reservations AS r "
                            + "ON r.order_item_id = oi.id AND r.state = 'active' "
                            + "WHERE oi.order_id = ? AND ("
                            + "r.id IS NULL OR r.quantity <> oi.quantity "
                            + "OR r.expires_at <= clock_timestamp())",
                    result -> result.getLong(1),
                    order.id
            );

            if (total.signum() <= 0 || invalidReservations != 0) {
                throw new BusinessException(
                        "Нет действующего полного резерва заказа."
                );
            }

            if (paid.add(value).compareTo(total) > 0) {
                throw new BusinessException(
                        "Сумма платежа превышает остаток к оплате."
                );
            }

            update(
                    connection,
                    "INSERT INTO public.payments "
                            + "(order_id, amount, external_ref, confirmed_by) "
                            + "VALUES (?, ?, ?, ?)",
                    order.id, value, paymentReference, actor
            );

            BigDecimal updatedPaid = paid.add(value);
            String status = updatedPaid.compareTo(total) == 0
                    ? "paid" : "awaiting_payment";

            update(
                    connection,
                    "UPDATE public.orders SET status = ? WHERE id = ?",
                    status, order.id
            );

            history(
                    connection, order.id, order.status, status,
                    actor, "Java: подтверждён платёж " + paymentReference
            );

            return new PaymentResult(
                    status, total, updatedPaid, false
            );
        });
    }

    public String prepare(
            String number,
            Map<String, Integer> picked,
            String login,
            char[] password
    ) throws SQLException {
        return transactions.execute(connection -> {
            long actor = authenticate(
                    connection, login, password, "warehouse"
            );

            OrderRepository.LockedOrder order =
                    repository.lockOrder(connection, number);

            if (!List.of("paid", "picking", "ready", "completed")
                    .contains(order.status)) {
                throw new InvalidOrderStateException(
                        "Комплектование разрешено после полной оплаты."
                );
            }

            List<Map.Entry<String, Integer>> items = list(
                    connection,
                    "SELECT p.sku, oi.quantity "
                            + "FROM public.order_items AS oi "
                            + "JOIN public.products AS p ON p.id = oi.product_id "
                            + "WHERE oi.order_id = ?",
                    result -> new AbstractMap.SimpleImmutableEntry<>(
                            result.getString("sku"),
                            result.getInt("quantity")
                    ),
                    order.id
            );

            Map<String, Integer> required = new LinkedHashMap<>();

            for (Map.Entry<String, Integer> item : items) {
                required.put(item.getKey(), item.getValue());
            }

            if (required.isEmpty() || !required.equals(picked)) {
                throw new BusinessException(
                        "Подобранные товары не совпадают с заказом."
                );
            }

            String status = order.status;

            if ("paid".equals(status)) {
                update(
                        connection,
                        "UPDATE public.orders SET status = 'picking' WHERE id = ?",
                        order.id
                );
                history(
                        connection, order.id, "paid", "picking",
                        actor, "Java: заказ принят на комплектование"
                );
                status = "picking";
            }

            if ("picking".equals(status)) {
                update(
                        connection,
                        "UPDATE public.orders SET status = 'ready' WHERE id = ?",
                        order.id
                );
                history(
                        connection, order.id, "picking", "ready",
                        actor, "Java: комплектность проверена"
                );
                status = "ready";
            }

            return status;
        });
    }

    public ShipmentResult ship(
            String number, String operationKey,
            String login, char[] password
    ) throws SQLException {
        if (operationKey == null || operationKey.isBlank()
                || operationKey.strip().length() > 64) {
            throw new BusinessException("Некорректный ключ отгрузки.");
        }

        final String key = operationKey.strip();

        return transactions.execute(connection -> {
            long actor = authenticate(
                    connection, login, password, "warehouse"
            );

            OrderRepository.LockedOrder order =
                    repository.lockOrder(connection, number);

            Map.Entry<Long, String> existing = one(
                    connection,
                    "SELECT id, operation_key FROM public.shipments "
                            + "WHERE order_id = ?",
                    result -> new AbstractMap.SimpleImmutableEntry<>(
                            result.getLong("id"),
                            result.getString("operation_key")
                    ),
                    order.id
            );

            if (existing != null) {
                if (!"completed".equals(order.status)
                        || !Objects.equals(existing.getValue(), key)) {
                    throw new InvalidOrderStateException(
                            "Заказ уже отгружен или имеет неверное состояние."
                    );
                }

                return new ShipmentResult(
                        existing.getKey(), true,
                        Collections.emptyList(),
                        repository.lockStock(connection, order)
                );
            }

            if (!"ready".equals(order.status)) {
                throw new InvalidOrderStateException(
                        "Заказ не готов к отгрузке."
                );
            }

            BigDecimal orderTotal = total(connection, order.id);

            if (orderTotal.signum() <= 0
                    || orderTotal.compareTo(paid(connection, order.id)) != 0) {
                throw new BusinessException("Заказ оплачен не полностью.");
            }

            List<OrderRepository.StockLine> before =
                    repository.lockStock(connection, order);

            if (before.isEmpty()) {
                throw new BusinessException("Заказ не содержит товаров.");
            }

            Map<Long, Long> reservationIds = new LinkedHashMap<>();

            for (OrderRepository.StockLine line : before) {
                long[] reservation = one(
                        connection,
                        "SELECT id, quantity FROM public.reservations "
                                + "WHERE order_item_id = ? AND state = 'active' "
                                + "FOR UPDATE",
                        result -> new long[]{
                                result.getLong("id"),
                                result.getLong("quantity")
                        },
                        line.itemId
                );

                if (reservation == null
                        || reservation[1] != line.quantity
                        || line.reserved < line.quantity
                        || line.onHand < line.quantity) {
                    throw new BusinessException(
                            "Неверный запас или резерв товара " + line.sku
                    );
                }

                reservationIds.put(line.itemId, reservation[0]);
            }

            long shipmentId = one(
                    connection,
                    "INSERT INTO public.shipments "
                            + "(order_id, warehouse_id, operation_key, shipped_by) "
                            + "VALUES (?, ?, ?, ?) RETURNING id",
                    result -> result.getLong("id"),
                    order.id, order.warehouseId, key, actor
            );

            for (OrderRepository.StockLine line : before) {
                long shipmentItemId = one(
                        connection,
                        "INSERT INTO public.shipment_items "
                                + "(shipment_id, order_id, warehouse_id, "
                                + "order_item_id, product_id, quantity) "
                                + "VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
                        result -> result.getLong("id"),
                        shipmentId, order.id, order.warehouseId,
                        line.itemId, line.productId, line.quantity
                );

                update(
                        connection,
                        "UPDATE public.stock_balances "
                                + "SET on_hand = on_hand - ?, "
                                + "reserved = reserved - ? "
                                + "WHERE warehouse_id = ? AND product_id = ?",
                        line.quantity, line.quantity,
                        order.warehouseId, line.productId
                );

                update(
                        connection,
                        "UPDATE public.reservations "
                                + "SET state = 'consumed', "
                                + "closed_at = clock_timestamp() WHERE id = ?",
                        reservationIds.get(line.itemId)
                );

                update(
                        connection,
                        "INSERT INTO public.stock_movements "
                                + "(warehouse_id, product_id, delta, "
                                + "shipment_item_id, reason, created_by) "
                                + "VALUES (?, ?, ?, ?, ?, ?)",
                        order.warehouseId, line.productId,
                        -line.quantity, shipmentItemId,
                        "Java: отгрузка заказа " + number, actor
                );
            }

            update(
                    connection,
                    "UPDATE public.orders SET status = 'completed' WHERE id = ?",
                    order.id
            );

            history(
                    connection, order.id, "ready", "completed",
                    actor, "Java: отгрузка " + key
            );

            return new ShipmentResult(
                    shipmentId, false, before,
                    repository.lockStock(connection, order)
            );
        });
    }

    private long authenticate(
            Connection connection, String login,
            char[] password, String role
    ) throws SQLException {
        long userId = authentication.authenticate(
                connection, login, password
        );
        authentication.requireRole(connection, userId, role);
        return userId;
    }

    private static BigDecimal total(Connection connection, long orderId)
            throws SQLException {
        return one(
                connection,
                "SELECT COALESCE(sum(quantity * unit_price), 0) "
                        + "FROM public.order_items WHERE order_id = ?",
                result -> result.getBigDecimal(1),
                orderId
        );
    }

    private static BigDecimal paid(Connection connection, long orderId)
            throws SQLException {
        return one(
                connection,
                "SELECT COALESCE(sum(amount), 0) "
                        + "FROM public.payments WHERE order_id = ?",
                result -> result.getBigDecimal(1),
                orderId
        );
    }

    private static BigDecimal parseAmount(String amount) {
        try {
            if (amount == null) {
                throw new NumberFormatException();
            }

            BigDecimal value = new BigDecimal(amount)
                    .setScale(2, RoundingMode.UNNECESSARY);

            if (value.signum() <= 0
                    || value.compareTo(
                            new BigDecimal("999999999999.99")
                    ) > 0) {
                throw new BusinessException("Недопустимая сумма платежа.");
            }

            return value;
        } catch (NumberFormatException | ArithmeticException exception) {
            throw new BusinessException("Некорректная сумма платежа.");
        }
    }

    private static void history(
            Connection connection, long orderId,
            String oldStatus, String newStatus, long actor, String reason
    ) throws SQLException {
        update(
                connection,
                "INSERT INTO public.order_history "
                        + "(order_id, old_status, new_status, changed_by, reason) "
                        + "VALUES (?, ?, ?, ?, ?)",
                orderId, oldStatus, newStatus, actor, reason
        );
    }

    public static final class PaymentResult {
        public final String status;
        public final BigDecimal total;
        public final BigDecimal paid;
        public final boolean repeated;

        public PaymentResult(
                String status, BigDecimal total,
                BigDecimal paid, boolean repeated
        ) {
            this.status = status;
            this.total = total;
            this.paid = paid;
            this.repeated = repeated;
        }
    }

    public static final class ShipmentResult {
        public final long shipmentId;
        public final boolean repeated;
        public final List<OrderRepository.StockLine> before;
        public final List<OrderRepository.StockLine> after;

        public ShipmentResult(
                long shipmentId, boolean repeated,
                List<OrderRepository.StockLine> before,
                List<OrderRepository.StockLine> after
        ) {
            this.shipmentId = shipmentId;
            this.repeated = repeated;
            this.before = before;
            this.after = after;
        }
    }
}