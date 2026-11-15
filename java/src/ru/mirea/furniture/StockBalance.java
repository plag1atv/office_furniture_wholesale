package ru.mirea.furniture;

public final class StockBalance {
    private final Product product;
    private int onHand;
    private int reserved;

    public StockBalance(Product product, int onHand, int reserved) {
        if (product == null) {
            throw new IllegalArgumentException("Не указан товар.");
        }

        if (onHand < 0 || reserved < 0 || reserved > onHand) {
            throw new IllegalArgumentException(
                    "Некорректный физический остаток или резерв."
            );
        }

        this.product = product;
        this.onHand = onHand;
        this.reserved = reserved;
    }

    public Product getProduct() {
        return product;
    }

    public int getOnHand() {
        return onHand;
    }

    public int getReserved() {
        return reserved;
    }

    public int getAvailable() {
        return onHand - reserved;
    }

    public void reserve(int quantity) {
        requirePositiveQuantity(quantity);

        if (quantity > getAvailable()) {
            throw new IllegalStateException(
                    "Недостаточно товара " + product.getSku()
                    + ": требуется " + quantity
                    + ", доступно " + getAvailable() + "."
            );
        }

        reserved += quantity;
    }

    public void release(int quantity) {
        requirePositiveQuantity(quantity);

        if (quantity > reserved) {
            throw new IllegalStateException(
                    "Нельзя освободить больше зарезервированного."
            );
        }

        reserved -= quantity;
    }

    public void ship(int quantity) {
        requirePositiveQuantity(quantity);

        if (quantity > reserved || quantity > onHand) {
            throw new IllegalStateException(
                    "Недостаточный запас или резерв для отгрузки."
            );
        }

        onHand -= quantity;
        reserved -= quantity;
    }

    public StockBalance copy() {
        return new StockBalance(product, onHand, reserved);
    }

    private static void requirePositiveQuantity(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Количество должно быть больше нуля."
            );
        }
    }
}