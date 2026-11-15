package ru.mirea.furniture;

import java.sql.Connection;
import java.sql.SQLException;

public interface TransactionManager {
    <T> T execute(Work<T> work) throws SQLException;

    @FunctionalInterface
    interface Work<T> {
        T run(Connection connection) throws SQLException;
    }
}