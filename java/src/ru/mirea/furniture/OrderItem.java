package ru.mirea.furniture;

import java.math.BigDecimal;

public final class OrderItem {
    private final Product product;
    private final int quantity;
    private final BigDecimal unitPrice;

    public OrderItem(Product product, int quantity) {
        if (product == null) {
            throw new IllegalArgumentException("Не указан товар.");
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Количество должно быть больше нуля."
            );
        }

        this.product = product;
        this.quantity = quantity;

        // Сохраняем цену, принятую при создании строки.
        this.unitPrice = product.getCataloguePrice();
    }

    public Product getProduct() {
        return product;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public BigDecimal getTotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}