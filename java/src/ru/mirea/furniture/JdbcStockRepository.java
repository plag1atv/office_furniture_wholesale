package ru.mirea.furniture;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class JdbcStockRepository implements StockRepository {
    private final DatabaseConnectionFactory connectionFactory;

    public JdbcStockRepository(
            DatabaseConnectionFactory connectionFactory
    ) {
        this.connectionFactory = connectionFactory;
    }

    @Override
    public List<StockBalance> findByWarehouse(String warehouseName)
            throws SQLException {
        String query =
                "SELECT p.sku, p.name, p.price, "
                + "sb.on_hand, sb.reserved "
                + "FROM public.stock_balances AS sb "
                + "JOIN public.products AS p ON p.id = sb.product_id "
                + "JOIN public.warehouses AS w ON w.id = sb.warehouse_id "
                + "WHERE w.name = ? "
                + "ORDER BY p.sku";

        List<StockBalance> balances = new ArrayList<>();

        try (
                Connection connection = connectionFactory.openConnection();
                PreparedStatement statement = connection.prepareStatement(query)
        ) {
            statement.setString(1, warehouseName);

            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    Product product = new Product(
                            result.getString("sku"),
                            result.getString("name"),
                            result.getBigDecimal("price").toPlainString()
                    );

                    balances.add(
                            new StockBalance(
                                    product,
                                    result.getInt("on_hand"),
                                    result.getInt("reserved")
                            )
                    );
                }
            }
        }

        return Collections.unmodifiableList(balances);
    }
}