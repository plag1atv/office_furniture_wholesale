package ru.mirea.furniture;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class JdbcAuthenticationService {
    public long authenticate(
            Connection connection,
            String login,
            char[] password
    ) throws SQLException {
        if (login == null || login.isBlank()
                || password == null || password.length == 0) {
            throw new BusinessException("Неверный логин или пароль.");
        }

        String query =
                "SELECT id, password_hash, active "
                + "FROM public.users WHERE login = ? FOR SHARE";

        long userId;
        String storedHash;
        boolean active;

        try (PreparedStatement statement =
                     connection.prepareStatement(query)) {
            statement.setString(1, login.strip());

            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    throw new BusinessException(
                            "Неверный логин или пароль."
                    );
                }

                userId = result.getLong("id");
                storedHash = result.getString("password_hash");
                active = result.getBoolean("active");
            }
        }

        if (!verifyPassword(password, storedHash)) {
            throw new BusinessException("Неверный логин или пароль.");
        }

        if (!active) {
            throw new BusinessException("Учётная запись отключена.");
        }

        return userId;
    }

    public void requireRole(
            Connection connection,
            long userId,
            String roleName
    ) throws SQLException {
        String query =
                "SELECT EXISTS ("
                + "SELECT 1 FROM public.user_roles AS ur "
                + "JOIN public.roles AS r ON r.id = ur.role_id "
                + "JOIN public.users AS u ON u.id = ur.user_id "
                + "WHERE ur.user_id = ? AND r.name = ? AND u.active"
                + ")";

        try (PreparedStatement statement =
                     connection.prepareStatement(query)) {
            statement.setLong(1, userId);
            statement.setString(2, roleName);

            try (ResultSet result = statement.executeQuery()) {
                result.next();

                if (!result.getBoolean(1)) {
                    throw new BusinessException(
                            "Для операции требуется роль: " + roleName
                    );
                }
            }
        }
    }

    private boolean verifyPassword(char[] password, String storedHash) {
        if (storedHash == null) {
            return false;
        }

        String[] parts = storedHash.split("\\$", -1);

        if (parts.length != 4
                || !"pbkdf2_sha256".equals(parts[0])
                || !"600000".equals(parts[1])) {
            return false;
        }

        byte[] salt;
        byte[] expected;

        try {
            salt = decodeHex(parts[2]);
            expected = decodeHex(parts[3]);
        } catch (IllegalArgumentException exception) {
            return false;
        }

        if (salt.length != 16 || expected.length != 32) {
            return false;
        }

        PBEKeySpec specification = new PBEKeySpec(
                password, salt, 600_000, 256
        );

        try {
            byte[] actual = SecretKeyFactory
                    .getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(specification)
                    .getEncoded();

            return MessageDigest.isEqual(actual, expected);
        } catch (GeneralSecurityException exception) {
            throw new BusinessException(
                    "Не удалось выполнить проверку хеша пароля."
            );
        } finally {
            specification.clearPassword();
        }
    }

    private byte[] decodeHex(String text) {
        if (text.length() % 2 != 0) {
            throw new IllegalArgumentException("Некорректный HEX.");
        }

        byte[] result = new byte[text.length() / 2];

        for (int i = 0; i < result.length; i++) {
            int high = Character.digit(text.charAt(i * 2), 16);
            int low = Character.digit(text.charAt(i * 2 + 1), 16);

            if (high < 0 || low < 0) {
                throw new IllegalArgumentException("Некорректный HEX.");
            }

            result[i] = (byte) ((high << 4) | low);
        }

        return result;
    }
}