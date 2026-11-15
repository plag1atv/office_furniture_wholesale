BEGIN;

-- 11. Заказы покупателей.
CREATE TABLE public.orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    number VARCHAR(40) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL
        REFERENCES public.customers (id) ON DELETE RESTRICT,
    contact_id BIGINT,
    warehouse_id BIGINT NOT NULL
        REFERENCES public.warehouses (id) ON DELETE RESTRICT,
    manager_id BIGINT NOT NULL
        REFERENCES public.users (id) ON DELETE RESTRICT,
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reserve_key VARCHAR(64) UNIQUE,

    CONSTRAINT fk_orders_customer_contact
        FOREIGN KEY (contact_id, customer_id)
        REFERENCES public.customer_contacts (id, customer_id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_orders_id_warehouse
        UNIQUE (id, warehouse_id),

    CONSTRAINT ck_orders_number
        CHECK (length(btrim(number)) > 0),

    CONSTRAINT ck_orders_status
        CHECK (
            status IN (
                'draft',
                'awaiting_payment',
                'paid',
                'picking',
                'ready',
                'completed',
                'cancelled'
            )
        ),

    CONSTRAINT ck_orders_reserve_key
        CHECK (
            reserve_key IS NULL
            OR length(btrim(reserve_key)) > 0
        )
);

-- 12. Строки заказа.
CREATE TABLE public.order_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES public.orders (id) ON DELETE RESTRICT,
    product_id BIGINT NOT NULL
        REFERENCES public.products (id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,

    CONSTRAINT uq_order_items_product
        UNIQUE (order_id, product_id),

    CONSTRAINT uq_order_items_identity
        UNIQUE (id, order_id, product_id),

    CONSTRAINT ck_order_items_quantity
        CHECK (quantity > 0),

    CONSTRAINT ck_order_items_price
        CHECK (
            unit_price >= 0
            AND unit_price <> 'NaN'::NUMERIC
        )
);

-- 13. Резервы товаров.
CREATE TABLE public.reservations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_item_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    warehouse_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    state VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ,

    CONSTRAINT fk_reservations_order_item
        FOREIGN KEY (order_item_id, order_id, product_id)
        REFERENCES public.order_items (id, order_id, product_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_reservations_order_warehouse
        FOREIGN KEY (order_id, warehouse_id)
        REFERENCES public.orders (id, warehouse_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_reservations_stock
        FOREIGN KEY (warehouse_id, product_id)
        REFERENCES public.stock_balances (warehouse_id, product_id)
        ON DELETE RESTRICT,

    CONSTRAINT ck_reservations_quantity
        CHECK (quantity > 0),

    CONSTRAINT ck_reservations_state
        CHECK (state IN ('active', 'released', 'consumed', 'expired')),

    CONSTRAINT ck_reservations_expiration
        CHECK (expires_at > created_at),

    CONSTRAINT ck_reservations_closed_at
        CHECK (
            (state = 'active' AND closed_at IS NULL)
            OR
            (
                state <> 'active'
                AND closed_at IS NOT NULL
                AND closed_at >= created_at
            )
        )
);

-- У строки заказа может быть только один активный резерв.
-- Закрытые резервы остаются в истории.
CREATE UNIQUE INDEX uq_reservations_active_item
    ON public.reservations (order_item_id)
    WHERE state = 'active';

-- 14. Подтверждённые платежи.
CREATE TABLE public.payments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES public.orders (id) ON DELETE RESTRICT,
    amount NUMERIC(14, 2) NOT NULL,
    external_ref VARCHAR(100) NOT NULL UNIQUE,
    confirmed_by BIGINT NOT NULL
        REFERENCES public.users (id) ON DELETE RESTRICT,
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_payments_amount
        CHECK (
            amount > 0
            AND amount <> 'NaN'::NUMERIC
        ),

    CONSTRAINT ck_payments_external_ref
        CHECK (length(btrim(external_ref)) > 0)
);

-- 15. Заголовки отгрузок.
CREATE TABLE public.shipments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL UNIQUE,
    warehouse_id BIGINT NOT NULL,
    operation_key VARCHAR(64) NOT NULL UNIQUE,
    shipped_by BIGINT NOT NULL
        REFERENCES public.users (id) ON DELETE RESTRICT,
    shipped_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_shipments_order_warehouse
        FOREIGN KEY (order_id, warehouse_id)
        REFERENCES public.orders (id, warehouse_id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_shipments_identity
        UNIQUE (id, order_id, warehouse_id),

    CONSTRAINT ck_shipments_operation_key
        CHECK (length(btrim(operation_key)) > 0)
);

-- 16. Строки отгрузок.
CREATE TABLE public.shipment_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shipment_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    warehouse_id BIGINT NOT NULL,
    order_item_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,

    CONSTRAINT fk_shipment_items_shipment
        FOREIGN KEY (shipment_id, order_id, warehouse_id)
        REFERENCES public.shipments (id, order_id, warehouse_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_shipment_items_order_item
        FOREIGN KEY (order_item_id, order_id, product_id)
        REFERENCES public.order_items (id, order_id, product_id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_shipment_items_order_item
        UNIQUE (shipment_id, order_item_id),

    CONSTRAINT uq_shipment_items_stock_identity
        UNIQUE (id, warehouse_id, product_id),

    CONSTRAINT ck_shipment_items_quantity
        CHECK (quantity > 0)
);

-- 17. Движения товаров.
CREATE TABLE public.stock_movements (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    warehouse_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    delta INTEGER NOT NULL,
    shipment_item_id BIGINT UNIQUE,
    reason TEXT NOT NULL,
    created_by BIGINT NOT NULL
        REFERENCES public.users (id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_movements_stock
        FOREIGN KEY (warehouse_id, product_id)
        REFERENCES public.stock_balances (warehouse_id, product_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_movements_shipment_item
        FOREIGN KEY (shipment_item_id, warehouse_id, product_id)
        REFERENCES public.shipment_items (id, warehouse_id, product_id)
        ON DELETE RESTRICT,

    CONSTRAINT ck_movements_delta
        CHECK (delta <> 0),

    CONSTRAINT ck_movements_shipment_direction
        CHECK (shipment_item_id IS NULL OR delta < 0),

    CONSTRAINT ck_movements_reason
        CHECK (length(btrim(reason)) > 0)
);

-- 18. История изменения состояния заказов.
CREATE TABLE public.order_history (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES public.orders (id) ON DELETE RESTRICT,
    old_status VARCHAR(30),
    new_status VARCHAR(30) NOT NULL,
    changed_by BIGINT NOT NULL
        REFERENCES public.users (id) ON DELETE RESTRICT,
    reason TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_history_old_status
        CHECK (
            old_status IS NULL
            OR old_status IN (
                'draft', 'awaiting_payment', 'paid', 'picking',
                'ready', 'completed', 'cancelled'
            )
        ),

    CONSTRAINT ck_history_new_status
        CHECK (
            new_status IN (
                'draft', 'awaiting_payment', 'paid', 'picking',
                'ready', 'completed', 'cancelled'
            )
        ),

    CONSTRAINT ck_history_reason
        CHECK (length(btrim(reason)) > 0)
);

-- Индексы для поиска заказов и связанных записей.
CREATE INDEX ix_orders_customer
    ON public.orders (customer_id);

CREATE INDEX ix_orders_manager
    ON public.orders (manager_id);

CREATE INDEX ix_orders_status_created
    ON public.orders (status, created_at);

CREATE INDEX ix_order_items_product
    ON public.order_items (product_id);

CREATE INDEX ix_reservations_order
    ON public.reservations (order_id);

CREATE INDEX ix_reservations_active_expiration
    ON public.reservations (expires_at)
    WHERE state = 'active';

CREATE INDEX ix_payments_order
    ON public.payments (order_id);

CREATE INDEX ix_shipment_items_order_item
    ON public.shipment_items (order_item_id);

CREATE INDEX ix_movements_stock_created
    ON public.stock_movements (warehouse_id, product_id, created_at);

CREATE INDEX ix_history_order_changed
    ON public.order_history (order_id, changed_at);

COMMIT;