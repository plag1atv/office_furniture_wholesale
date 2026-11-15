package ru.mirea.furniture;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;

public final class Product {
    private final String sku;
    private final String name;
    private final BigDecimal cataloguePrice;

    public Product(String sku, String name, String price) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("Не указан артикул.");
        }

        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Не указано название товара.");
        }

        if (price == null) {
            throw new IllegalArgumentException("Не указана цена.");
        }

        BigDecimal parsedPrice;

        try {
            parsedPrice = new BigDecimal(price)
                    .setScale(2, RoundingMode.UNNECESSARY);
        } catch (NumberFormatException | ArithmeticException exception) {
            throw new IllegalArgumentException(
                    "Цена должна быть числом с точностью до копеек.",
                    exception
            );
        }

        if (parsedPrice.signum() < 0
                || parsedPrice.compareTo(
                        new BigDecimal("999999999999.99")
                ) > 0) {
            throw new IllegalArgumentException(
                    "Цена находится вне допустимого диапазона."
            );
        }

        this.sku = sku.strip().toUpperCase(Locale.ROOT);
        this.name = name.strip();
        this.cataloguePrice = parsedPrice;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getCataloguePrice() {
        return cataloguePrice;
    }
}