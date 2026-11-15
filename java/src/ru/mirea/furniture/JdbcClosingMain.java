package ru.mirea.furniture;

import java.io.Console;
import java.io.PrintStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.sql.SQLException;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

import static ru.mirea.furniture.JdbcSql.*;

public final class JdbcClosingMain {
    private static final String WAREHOUSE = "Java-сценарий 844d88cf";

    public static void main(String[] args) {
        System.setOut(
                new PrintStream(System.out, true, StandardCharsets.UTF_8)
        );
        System.setErr(
                new PrintStream(System.err, true, StandardCharsets.UTF_8)
        );

        char[] managerPassword = null;
        char[] accountantPassword = null;

        try {
            Console console = System.console();

            if (console == null) {
                throw new BusinessException("Запускай программу из терминала.");
            }

            managerPassword = console.readPassword("Password manager: ");
            accountantPassword = console.readPassword("Password accountant: ");

            DatabaseConnectionFactory factory =
                    new DatabaseConnectionFactory();

            TransactionManager transactions =
                    new JdbcTransactionManager(factory);

            OrderRepository repository = new JdbcOrderRepository();
            JdbcAuthenticationService authentication =
                    new JdbcAuthenticationService();

            JdbcOrderService orders = new JdbcOrderService(
                    transactions, repository, authentication
            );

            JdbcFulfillmentService fulfillment = new JdbcFulfillmentService(
                    transactions, repository, authentication
            );

            StockRepository stock = new JdbcStockRepository(factory);

            List<StockBalance> balances = stock.findByWarehouse(WAREHOUSE);

            Product chair = balances.stream()
                    .map(StockBalance::getProduct)
                    .filter(product -> "KR-01".equals(product.getSku()))
                    .findFirst()
                    .orElseThrow(
                            () -> new BusinessException("Кресло не найдено.")
                    );

            String before = signature(balances);
            String suffix = UUID.randomUUID().toString().substring(0, 8);

            String cancelNumber = "JAVA-CANCEL-" + suffix;
            String expireNumber = "JAVA-EXPIRE-" + suffix;

            System.out.println("1. ОТМЕНА ЧАСТИЧНО ОПЛАЧЕННОГО ЗАКАЗА");

            createAndReserve(
                    orders, chair, cancelNumber, managerPassword
            );

            fulfillment.pay(
                    cancelNumber,
                    "PAY-" + cancelNumber,
                    "1000.00",
                    "accountant",
                    accountantPassword
            );

            JdbcFulfillmentService.ClosingResult cancelled =
                    fulfillment.closeOrder(
                            cancelNumber,
                            "cancel",
                            "Учебная проверка отмены",
                            "manager",
                            managerPassword
                    );

            if (!cancelled.changed
                    || !"cancelled".equals(cancelled.status)
                    || cancelled.paid.compareTo(
                            new BigDecimal("1000.00")
                    ) != 0
                    || !cancelled.settlementRequired) {
                throw new AssertionError("Неверный результат отмены.");
            }

            System.out.println("Статус: " + cancelled.status);
            System.out.println("Платежи сохранены: " + cancelled.paid);
            System.out.println(
                    "Требуется урегулирование: "
                    + cancelled.settlementRequired
            );

            JdbcFulfillmentService.ClosingResult repeated =
                    fulfillment.closeOrder(
                            cancelNumber,
                            "cancel",
                            "Повторная отмена",
                            "manager",
                            managerPassword
                    );

            if (repeated.changed) {
                throw new AssertionError("Повторная отмена изменила данные.");
            }

            System.out.println("Повторная отмена не изменила данные.");

            System.out.println();
            System.out.println("2. ИСТЕЧЕНИЕ РЕЗЕРВА");

            createAndReserve(
                    orders, chair, expireNumber, managerPassword
            );

            final char[] managerSecret = managerPassword;

            // Искусственно истёкший резерв только нового тестового заказа.
            transactions.execute(connection -> {
                long actor = authentication.authenticate(
                        connection, "manager", managerSecret
                );
                authentication.requireRole(connection, actor, "manager");

                OrderRepository.LockedOrder order =
                        repository.lockOrder(connection, expireNumber);

                if (order.managerId != actor
                        || !"awaiting_payment".equals(order.status)) {
                    throw new BusinessException(
                            "Неверное состояние тестового заказа."
                    );
                }

                update(
                        connection,
                        "UPDATE public.reservations "
                                + "SET created_at = clock_timestamp() "
                                + "- INTERVAL '2 hours', "
                                + "expires_at = clock_timestamp() "
                                + "- INTERVAL '1 hour' "
                                + "WHERE order_id = ? AND state = 'active'",
                        order.id
                );

                return null;
            });

            JdbcFulfillmentService.ClosingResult expired =
                    fulfillment.closeOrder(
                            expireNumber,
                            "expire",
                            "Истёк срок тестового резерва",
                            "manager",
                            managerPassword
                    );

            if (!expired.changed || !"draft".equals(expired.status)) {
                throw new AssertionError("Резерв не освобождён.");
            }

            System.out.println("Статус после истечения: " + expired.status);

            // Завершаем тестовый черновик обычной отменой.
            fulfillment.closeOrder(
                    expireNumber,
                    "cancel",
                    "Проверка завершена",
                    "manager",
                    managerPassword
            );

            System.out.println();
            System.out.println("3. ЗАПРЕТ ОТМЕНЫ ОТГРУЖЕННОГО ЗАКАЗА");

            try {
                fulfillment.closeOrder(
                        "JAVA-DB-844d88cf",
                        "cancel",
                        "Попытка отмены после отгрузки",
                        "manager",
                        managerPassword
                );
                throw new AssertionError(
                        "Отмена завершённого заказа разрешена."
                );
            } catch (InvalidOrderStateException exception) {
                System.out.println("Ожидаемый отказ: " + exception.getMessage());
            }

            List<StockBalance> after = stock.findByWarehouse(WAREHOUSE);

            if (!before.equals(signature(after))) {
                throw new AssertionError("Тесты изменили итоговые остатки.");
            }

            System.out.println();
            System.out.println("ИТОГОВЫЕ ОСТАТКИ");

            for (StockBalance balance : after) {
                System.out.printf(
                        "%s: наличие=%d, резерв=%d, доступно=%d%n",
                        balance.getProduct().getSku(),
                        balance.getOnHand(),
                        balance.getReserved(),
                        balance.getAvailable()
                );
            }

            System.out.println();
            System.out.println(
                    "Проверки отмены и истечения резерва Java пройдены."
            );

        } catch (SQLException | BusinessException exception) {
            System.err.println("Ошибка: " + exception.getMessage());
            System.exit(1);
        } finally {
            if (managerPassword != null) {
                Arrays.fill(managerPassword, '\0');
            }
            if (accountantPassword != null) {
                Arrays.fill(accountantPassword, '\0');
            }
        }
    }

    private static void createAndReserve(
            JdbcOrderService service,
            Product product,
            String number,
            char[] password
    ) throws SQLException {
        Order order = new Order(
                number,
                "Учебный покупатель",
                Collections.singletonList(new OrderItem(product, 1))
        );

        service.createDraft(
                order, "0000000001", WAREHOUSE, "manager", password
        );

        service.reserve(
                number, "RESERVE-" + number, "manager", password
        );
    }

    private static String signature(List<StockBalance> balances) {
        return balances.stream()
                .map(balance ->
                        balance.getProduct().getSku()
                        + ":" + balance.getOnHand()
                        + ":" + balance.getReserved()
                )
                .sorted()
                .collect(Collectors.joining("|"));
    }
}