package ru.mirea.furniture;

import java.io.Console;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.sql.SQLException;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;

import static ru.mirea.furniture.JdbcSql.*;

public final class JdbcOrdersMain {
    public static void main(String[] args) {
        System.setOut(
                new PrintStream(System.out, true, StandardCharsets.UTF_8)
        );
        System.setErr(
                new PrintStream(System.err, true, StandardCharsets.UTF_8)
        );

        char[] password = null;

        try {
            Console console = System.console();

            if (console == null) {
                throw new BusinessException("Запускай программу из терминала.");
            }

            String login = console.readLine("Login: ");
            password = console.readPassword("Password: ");
            final char[] enteredPassword = password;

            DatabaseConnectionFactory factory =
                    new DatabaseConnectionFactory();

            TransactionManager transactions =
                    new JdbcTransactionManager(factory);

            JdbcAuthenticationService authentication =
                    new JdbcAuthenticationService();

            JdbcOrderService service = new JdbcOrderService(
                    transactions,
                    new JdbcOrderRepository(),
                    authentication
            );

            String suffix = UUID.randomUUID().toString().substring(0, 8);
            String warehouseName = "Java-сценарий " + suffix;

            // Создаём отдельный демонстрационный склад.
            transactions.execute(connection -> {
                long userId = authentication.authenticate(
                        connection, login, enteredPassword
                );
                authentication.requireRole(connection, userId, "manager");

                long warehouseId = one(
                        connection,
                        "INSERT INTO public.warehouses (name, address) "
                                + "VALUES (?, ?) RETURNING id",
                        result -> result.getLong("id"),
                        warehouseName, "Учебный склад Java"
                );

                for (String sku : Arrays.asList("ST-01", "KR-01")) {
                    int quantity = "ST-01".equals(sku) ? 10 : 20;

                    int inserted = update(
                            connection,
                            "INSERT INTO public.stock_balances "
                                    + "(warehouse_id, product_id, on_hand, reserved) "
                                    + "SELECT ?, id, ?, 0 FROM public.products "
                                    + "WHERE sku = ? AND active",
                            warehouseId, quantity, sku
                    );

                    if (inserted != 1) {
                        throw new BusinessException("Не найден товар " + sku);
                    }
                }

                return warehouseId;
            });

            StockRepository stockRepository = new JdbcStockRepository(factory);
            List<StockBalance> initial =
                    stockRepository.findByWarehouse(warehouseName);

            Product table = findProduct(initial, "ST-01");
            Product chair = findProduct(initial, "KR-01");

            String backgroundNumber = "JAVA-BACK-" + suffix;
            String mainNumber = "JAVA-DB-" + suffix;

            Order background = new Order(
                    backgroundNumber,
                    "Учебный покупатель",
                    Arrays.asList(
                            new OrderItem(table, 2),
                            new OrderItem(chair, 5)
                    )
            );

            service.createDraft(
                    background, "0000000001", warehouseName,
                    login, enteredPassword
            );
            service.reserve(
                    backgroundNumber, "RESERVE-" + backgroundNumber,
                    login, enteredPassword
            );

            Order mainOrder = new Order(
                    mainNumber,
                    "Учебный покупатель",
                    Arrays.asList(
                            new OrderItem(table, 3),
                            new OrderItem(chair, 4)
                    )
            );

            service.createDraft(
                    mainOrder, "0000000001", warehouseName,
                    login, enteredPassword
            );

            boolean created = service.reserve(
                    mainNumber, "RESERVE-" + mainNumber,
                    login, enteredPassword
            );

            boolean repeated = service.reserve(
                    mainNumber, "RESERVE-" + mainNumber,
                    login, enteredPassword
            );

            if (!created || repeated) {
                throw new AssertionError("Нарушена обработка повтора.");
            }

            System.out.println();
            System.out.println("ЗАКАЗЫ JAVA СОХРАНЕНЫ В POSTGRESQL");
            System.out.println("Склад: " + warehouseName);
            System.out.println("Фоновый заказ: " + backgroundNumber);
            System.out.println("Основной заказ: " + mainNumber);
            System.out.println("Стоимость основного: " + mainOrder.getTotal());
            System.out.println("Статус в базе: awaiting_payment");

            System.out.println();
            System.out.println("ОСТАТКИ ПОСЛЕ ДВУХ РЕЗЕРВИРОВАНИЙ");

            for (StockBalance balance
                    : stockRepository.findByWarehouse(warehouseName)) {
                System.out.printf(
                        "%s: наличие=%d, резерв=%d, доступно=%d%n",
                        balance.getProduct().getSku(),
                        balance.getOnHand(),
                        balance.getReserved(),
                        balance.getAvailable()
                );
            }

            System.out.println();
            System.out.println("Повтор основного резерва не изменил данные.");

        } catch (SQLException | BusinessException exception) {
            System.err.println("Ошибка: " + exception.getMessage());
            System.exit(1);
        } finally {
            if (password != null) {
                Arrays.fill(password, '\0');
            }
        }
    }

    private static Product findProduct(
            List<StockBalance> balances, String sku
    ) {
        return balances.stream()
                .map(StockBalance::getProduct)
                .filter(product -> sku.equals(product.getSku()))
                .findFirst()
                .orElseThrow(
                        () -> new BusinessException("Не найден товар " + sku)
                );
    }
}