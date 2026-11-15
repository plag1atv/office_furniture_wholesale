package ru.mirea.furniture;

public final class InvalidOrderStateException extends BusinessException {
    public InvalidOrderStateException(String message) {
        super(message);
    }
}