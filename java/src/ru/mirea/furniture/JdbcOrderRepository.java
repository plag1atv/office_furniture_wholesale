package ru.mirea.furniture;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

import static ru.mirea.furniture.JdbcSql.*;

public final class JdbcOrderRepository implements OrderRepository {
    @Override
    public long createDraft(
            Connection connection,
            Order order,
            String customerInn,
            String warehouseName,
            long managerId
    ) throws SQLException {
        Long customerId = one(
                connection,
                "SELECT id FROM public.customers "
                        + "WHERE inn = ? AND active FOR SHARE",
                result -> result.getLong("id"),
                customerInn
        );

        Long warehouseId = one(
                connection,
                "SELECT id FROM public.warehouses WHERE name = ?",
                result -> result.getLong("id"),
                warehouseName
        );

        if (customerId == null || warehouseId == null) {
            throw new BusinessException("Покупатель или склад не найден.");
        }

        long orderId = one(
                connection,
                "INSERT INTO public.orders "
                        + "(number, customer_id, warehouse_id, manager_id, status) "
                        + "VALUES (?, ?, ?, ?, 'draft') RETURNING id",
                result -> result.getLong("id"),
                order.getNumber(), customerId, warehouseId, managerId
        );

        for (OrderItem item : order.getItems()) {
            Long productId = one(
                    connection,
                    "SELECT id FROM public.products "
                            + "WHERE sku = ? AND active FOR SHARE",
                    result -> result.getLong("id"),
                    item.getProduct().getSku()
            );

            if (productId == null) {
                throw new BusinessException(
                        "Товар не найден: " + item.getProduct().getSku()
                );
            }

            update(
                    connection,
                    "INSERT INTO public.order_items "
                            + "(order_id, product_id, quantity, unit_price) "
                            + "VALUES (?, ?, ?, ?)",
                    orderId, productId,
                    item.getQuantity(), item.getUnitPrice()
            );
        }

        update(
                connection,
                "INSERT INTO public.order_history "
                        + "(order_id, old_status, new_status, changed_by, reason) "
                        + "VALUES (?, NULL, 'draft', ?, ?)",
                orderId, managerId, "Создан черновик средствами Java"
        );

        return orderId;
    }

    @Override
    public LockedOrder lockOrder(Connection connection, String number)
            throws SQLException {
        LockedOrder order = one(
                connection,
                "SELECT id, warehouse_id, manager_id, status, reserve_key "
                        + "FROM public.orders WHERE number = ? FOR UPDATE",
                result -> new LockedOrder(
                        result.getLong("id"),
                        result.getLong("warehouse_id"),
                        result.getLong("manager_id"),
                        result.getString("status"),
                        result.getString("reserve_key")
                ),
                number
        );

        if (order == null) {
            throw new BusinessException("Заказ не найден.");
        }

        return order;
    }

    @Override
    public List<StockLine> lockStock(
            Connection connection, LockedOrder order
    ) throws SQLException {
        List<StockLine> items = list(
                connection,
                "SELECT oi.id, oi.product_id, oi.quantity, p.sku "
                        + "FROM public.order_items AS oi "
                        + "JOIN public.products AS p ON p.id = oi.product_id "
                        + "WHERE oi.order_id = ? ORDER BY oi.product_id",
                result -> new StockLine(
                        result.getLong("id"),
                        result.getLong("product_id"),
                        result.getString("sku"),
                        result.getInt("quantity"),
                        0,
                        0
                ),
                order.id
        );

        List<StockLine> locked = new ArrayList<>();

        for (StockLine item : items) {
            int[] balance = one(
                    connection,
                    "SELECT on_hand, reserved FROM public.stock_balances "
                            + "WHERE warehouse_id = ? AND product_id = ? "
                            + "FOR UPDATE",
                    result -> new int[]{
                            result.getInt("on_hand"),
                            result.getInt("reserved")
                    },
                    order.warehouseId, item.productId
            );

            if (balance == null) {
                throw new InsufficientStockException(
                        "Нет складской записи товара " + item.sku
                );
            }

            locked.add(new StockLine(
                    item.itemId, item.productId, item.sku,
                    item.quantity, balance[0], balance[1]
            ));
        }

        return locked;
    }

    @Override
    public void saveReservation(
            Connection connection,
            LockedOrder order,
            List<StockLine> lines,
            String operationKey,
            long userId
    ) throws SQLException {
        for (StockLine line : lines) {
            update(
                    connection,
                    "UPDATE public.stock_balances "
                            + "SET reserved = reserved + ? "
                            + "WHERE warehouse_id = ? AND product_id = ?",
                    line.quantity, order.warehouseId, line.productId
            );

            update(
                    connection,
                    "INSERT INTO public.reservations "
                            + "(order_item_id, order_id, warehouse_id, "
                            + "product_id, quantity, state, expires_at) "
                            + "VALUES (?, ?, ?, ?, ?, 'active', "
                            + "clock_timestamp() + INTERVAL '24 hours')",
                    line.itemId, order.id, order.warehouseId,
                    line.productId, line.quantity
            );
        }

        update(
                connection,
                "UPDATE public.orders "
                        + "SET status = 'awaiting_payment', reserve_key = ? "
                        + "WHERE id = ?",
                operationKey, order.id
        );

        update(
                connection,
                "INSERT INTO public.order_history "
                        + "(order_id, old_status, new_status, changed_by, reason) "
                        + "VALUES (?, 'draft', 'awaiting_payment', ?, ?)",
                order.id, userId, "Создан резерв средствами Java"
        );
    }
}