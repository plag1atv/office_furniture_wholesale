package ru.mirea.furniture;

public final class InsufficientStockException extends BusinessException {
    public InsufficientStockException(String message) {
        super(message);
    }
}