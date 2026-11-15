package ru.mirea.furniture;

public class BusinessException extends RuntimeException {
    public BusinessException(String message) {
        super(message);
    }
}