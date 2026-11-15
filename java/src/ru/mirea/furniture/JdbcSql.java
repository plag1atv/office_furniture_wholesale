 package ru.mirea.furniture;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public final class JdbcSql {
    private JdbcSql() {
    }

    @FunctionalInterface
    public interface Mapper<T> {
        T map(ResultSet result) throws SQLException;
    }

    public static int update(
            Connection connection, String query, Object... parameters
    ) throws SQLException {
        try (PreparedStatement statement =
                     connection.prepareStatement(query)) {
            bind(statement, parameters);
            return statement.executeUpdate();
        }
    }

    public static <T> List<T> list(
            Connection connection,
            String query,
            Mapper<T> mapper,
            Object... parameters
    ) throws SQLException {
        List<T> records = new ArrayList<>();

        try (PreparedStatement statement =
                     connection.prepareStatement(query)) {
            bind(statement, parameters);

            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    records.add(mapper.map(result));
                }
            }
        }

        return records;
    }

    public static <T> T one(
            Connection connection,
            String query,
            Mapper<T> mapper,
            Object... parameters
    ) throws SQLException {
        List<T> records = list(connection, query, mapper, parameters);

        if (records.size() > 1) {
            throw new BusinessException("Запрос вернул несколько записей.");
        }

        return records.isEmpty() ? null : records.get(0);
    }

    private static void bind(
            PreparedStatement statement, Object[] parameters
    ) throws SQLException {
        for (int i = 0; i < parameters.length; i++) {
            statement.setObject(i + 1, parameters[i]);
        }
    }
}