package ru.mirea.furniture;

import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;

public final class JdbcMain {
    public static void main(String[] args) {
        System.setOut(
                new PrintStream(System.out, true, StandardCharsets.UTF_8)
        );
        System.setErr(
                new PrintStream(System.err, true, StandardCharsets.UTF_8)
        );

        try {
            DatabaseConnectionFactory factory =
                    new DatabaseConnectionFactory();

            System.out.println("ПОДКЛЮЧЕНИЕ JAVA К POSTGRESQL");

            try (Connection connection = factory.openConnection()) {
                System.out.println("База: " + connection.getCatalog());
                System.out.println(
                        "Пользователь: "
                        + connection.getMetaData().getUserName()
                );
                System.out.println(
                        "Версия сервера: "
                        + connection.getMetaData().getDatabaseProductVersion()
                );

                try (
                        Statement statement = connection.createStatement();
                        ResultSet result = statement.executeQuery(
                                "SELECT count(*) "
                                + "FROM information_schema.tables "
                                + "WHERE table_schema = 'public' "
                                + "AND table_type = 'BASE TABLE'"
                        )
                ) {
                    result.next();
                    int tableCount = result.getInt(1);

                    System.out.println("Количество таблиц: " + tableCount);

                    if (tableCount != 18) {
                        throw new BusinessException(
                                "Ожидалось 18 таблиц."
                        );
                    }
                }
            }

            StockRepository repository = new JdbcStockRepository(factory);
            List<StockBalance> balances =
                    repository.findByWarehouse("Основной");

            if (balances.isEmpty()) {
                throw new BusinessException(
                        "Остатки склада «Основной» не найдены."
                );
            }

            System.out.println();
            System.out.println("РЕАЛЬНЫЕ ОСТАТКИ СКЛАДА «ОСНОВНОЙ»");

            for (StockBalance balance : balances) {
                System.out.printf(
                        "%s: наличие=%d, резерв=%d, доступно=%d%n",
                        balance.getProduct().getSku(),
                        balance.getOnHand(),
                        balance.getReserved(),
                        balance.getAvailable()
                );
            }

            System.out.println();
            System.out.println("Чтение через StockRepository выполнено.");

        } catch (SQLException exception) {
            System.err.println(
                    "Ошибка PostgreSQL: " + exception.getMessage()
            );
            System.exit(1);
        } catch (BusinessException exception) {
            System.err.println("Ошибка: " + exception.getMessage());
            System.exit(1);
        }
    }
}