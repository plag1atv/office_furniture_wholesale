package ru.mirea.furniture;

public enum OrderStatus {
    DRAFT("Черновик"),
    AWAITING_PAYMENT("Ожидает оплаты"),
    PAID("Оплачен"),
    PICKING("Комплектуется"),
    READY("Готов к отгрузке"),
    COMPLETED("Завершён"),
    CANCELLED("Отменён");

    private final String title;

    OrderStatus(String title) {
        this.title = title;
    }

    @Override
    public String toString() {
        return title;
    }
}