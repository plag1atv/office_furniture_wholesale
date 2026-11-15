package ru.mirea.furniture;

import io.github.cdimascio.dotenv.Dotenv;

import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public final class DatabaseConnectionFactory {
    private final String url;
    private final Properties properties;

    public DatabaseConnectionFactory() {
        Path root = Path.of("").toAbsolutePath().normalize();

        if (!Files.isRegularFile(root.resolve(".env"))) {
            throw new BusinessException(
                    "Файл .env не найден. Запускай программу из корня проекта."
            );
        }

        Dotenv dotenv;

        try {
            dotenv = Dotenv.configure()
                    .directory(root.toString())
                    .load();
        } catch (RuntimeException exception) {
            throw new BusinessException(
                    "Не удалось прочитать .env. Проверь формат и кодировку."
            );
        }

        String host = requireSetting(dotenv, "DB_HOST");
        String database = requireSetting(dotenv, "DB_NAME");
        String user = requireSetting(dotenv, "DB_USER");
        String password = readPassword(dotenv, root);

        int port;

        try {
            port = Integer.parseInt(requireSetting(dotenv, "DB_PORT"));
        } catch (NumberFormatException exception) {
            throw new BusinessException("DB_PORT должен быть целым числом.");
        }

        if (port < 1 || port > 65535) {
            throw new BusinessException("Некорректный номер порта.");
        }

        url = "jdbc:postgresql://" + host + ":" + port + "/" + database;

        properties = new Properties();
        properties.setProperty("user", user);
        properties.setProperty("password", password);
        properties.setProperty("connectTimeout", "5");
        properties.setProperty("ApplicationName", "office_furniture_java");
    }

    public Connection openConnection() throws SQLException {
        return DriverManager.getConnection(url, properties);
    }

    private static String requireSetting(Dotenv dotenv, String name) {
        String value = dotenv.get(name);

        if (value == null || value.isEmpty()) {
            throw new BusinessException("Не заполнена настройка " + name);
        }

        return value;
    }


        private static String readPassword(Dotenv dotenv, Path root) {
        String value = requireSetting(dotenv, "DB_PASSWORD");

        // Переменная среды уже содержит готовое значение пароля.
        if (System.getenv("DB_PASSWORD") != null) {
            return value;
        }

        String rawValue = null;

        try {
            for (String line : Files.readAllLines(
                    root.resolve(".env"), StandardCharsets.UTF_8
            )) {
                int separator = line.indexOf('=');

                if (separator >= 0
                        && line.substring(0, separator).strip()
                                .equals("DB_PASSWORD")) {
                    rawValue = line.substring(separator + 1).strip();
                }
            }
        } catch (IOException exception) {
            throw new BusinessException("Не удалось прочитать настройки.");
        }

        // Обрабатываем формат одинарных кавычек,
        // использованный в нашем .env.
        if (rawValue != null
                && rawValue.length() >= 2
                && rawValue.startsWith("'")
                && rawValue.endsWith("'")) {
            String text = rawValue.substring(1, rawValue.length() - 1);
            StringBuilder decoded = new StringBuilder();

            for (int i = 0; i < text.length(); i++) {
                char character = text.charAt(i);

                if (character == '\\' && i + 1 < text.length()) {
                    char next = text.charAt(i + 1);

                    if (next == '\\' || next == '\'') {
                        decoded.append(next);
                        i++;
                        continue;
                    }
                }

                decoded.append(character);
            }

            value = decoded.toString();
        }

        if (value.isEmpty()) {
            throw new BusinessException("Не заполнена настройка DB_PASSWORD.");
        }

        return value;
    }
}