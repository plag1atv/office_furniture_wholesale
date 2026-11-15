package ru.mirea.furniture;

import java.sql.SQLException;
import java.util.List;

public interface StockRepository {
    List<StockBalance> findByWarehouse(String warehouseName)
            throws SQLException;
}