package ru.mirea.furniture;

import java.io.Console;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.sql.SQLException;
import java.util.Arrays;

public final class JdbcSecurityMain {
    public static void main(String[] args) {
        System.setOut(
                new PrintStream(System.out, true, StandardCharsets.UTF_8)
        );
        System.setErr(
                new PrintStream(System.err, true, StandardCharsets.UTF_8)
        );

        char[] password = null;

        try {
            Console console = System.console();

            if (console == null) {
                throw new BusinessException(
                        "Недоступен скрытый ввод пароля. "
                        + "Запускай программу из терминала."
                );
            }

            System.out.println("ПРОВЕРКА ПОЛЬЗОВАТЕЛЯ JAVA");
            String login = console.readLine("Login: ");
            password = console.readPassword("Password: ");

            DatabaseConnectionFactory factory =
                    new DatabaseConnectionFactory();

            TransactionManager transactions =
                    new JdbcTransactionManager(factory);

            JdbcAuthenticationService authentication =
                    new JdbcAuthenticationService();

            final char[] enteredPassword = password;

            long userId = transactions.execute(connection -> {
                long authenticatedId = authentication.authenticate(
                        connection, login, enteredPassword
                );

                authentication.requireRole(
                        connection, authenticatedId, "manager"
                );

                return authenticatedId;
            });

            System.out.println();
            System.out.println("Вход выполнен: " + login);
            System.out.println("Идентификатор пользователя: " + userId);
            System.out.println("Роль manager подтверждена.");
            System.out.println("Проверка выполнена через TransactionManager.");
            System.out.println("Данные заказов не изменялись.");

        } catch (SQLException | BusinessException exception) {
            System.err.println("Ошибка: " + exception.getMessage());
            System.exit(1);
        } finally {
            if (password != null) {
                Arrays.fill(password, '\0');
            }
        }
    }
}