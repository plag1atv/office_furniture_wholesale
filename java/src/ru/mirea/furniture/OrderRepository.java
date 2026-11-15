package ru.mirea.furniture;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.List;

public interface OrderRepository {
    long createDraft(
            Connection connection,
            Order order,
            String customerInn,
            String warehouseName,
            long managerId
    ) throws SQLException;

    LockedOrder lockOrder(Connection connection, String number)
            throws SQLException;

    List<StockLine> lockStock(
            Connection connection, LockedOrder order
    ) throws SQLException;

    void saveReservation(
            Connection connection,
            LockedOrder order,
            List<StockLine> lines,
            String operationKey,
            long userId
    ) throws SQLException;

    final class LockedOrder {
        public final long id;
        public final long warehouseId;
        public final long managerId;
        public final String status;
        public final String reserveKey;

        public LockedOrder(
                long id, long warehouseId, long managerId,
                String status, String reserveKey
        ) {
            this.id = id;
            this.warehouseId = warehouseId;
            this.managerId = managerId;
            this.status = status;
            this.reserveKey = reserveKey;
        }
    }

    final class StockLine {
        public final long itemId;
        public final long productId;
        public final String sku;
        public final int quantity;
        public final int onHand;
        public final int reserved;

        public StockLine(
                long itemId, long productId, String sku,
                int quantity, int onHand, int reserved
        ) {
            this.itemId = itemId;
            this.productId = productId;
            this.sku = sku;
            this.quantity = quantity;
            this.onHand = onHand;
            this.reserved = reserved;
        }
    }
}