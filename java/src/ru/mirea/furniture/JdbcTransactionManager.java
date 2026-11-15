package ru.mirea.furniture;

import java.sql.Connection;
import java.sql.SQLException;

public final class JdbcTransactionManager implements TransactionManager {
    private final DatabaseConnectionFactory connectionFactory;

    public JdbcTransactionManager(
            DatabaseConnectionFactory connectionFactory
    ) {
        this.connectionFactory = connectionFactory;
    }

    @Override
    public <T> T execute(Work<T> work) throws SQLException {
        try (Connection connection = connectionFactory.openConnection()) {
            connection.setAutoCommit(false);
            connection.setTransactionIsolation(
                    Connection.TRANSACTION_READ_COMMITTED
            );

            try {
                T result = work.run(connection);
                connection.commit();
                return result;
            } catch (SQLException | RuntimeException | Error failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }

                throw failure;
            }
        }
    }
}