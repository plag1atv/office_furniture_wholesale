BEGIN;

-- 1. Покупатели.
CREATE TABLE public.customers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    inn VARCHAR(12) NOT NULL,
    address TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT uq_customers_inn UNIQUE (inn),
    CONSTRAINT ck_customers_name
        CHECK (length(btrim(name)) > 0),
    CONSTRAINT ck_customers_inn
        CHECK (inn ~ '^([0-9]{10}|[0-9]{12})$')
);

-- 2. Контактные лица покупателей.
CREATE TABLE public.customer_contacts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    name VARCHAR(150) NOT NULL,
    phone VARCHAR(30),
    email VARCHAR(254),

    CONSTRAINT fk_contacts_customer
        FOREIGN KEY (customer_id)
        REFERENCES public.customers (id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_contacts_id_customer
        UNIQUE (id, customer_id),

    CONSTRAINT ck_contacts_name
        CHECK (length(btrim(name)) > 0)
);

-- 3. Поставщики.
CREATE TABLE public.suppliers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    inn VARCHAR(12) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT uq_suppliers_inn UNIQUE (inn),
    CONSTRAINT ck_suppliers_name
        CHECK (length(btrim(name)) > 0),
    CONSTRAINT ck_suppliers_inn
        CHECK (inn ~ '^([0-9]{10}|[0-9]{12})$')
);

-- 4. Категории мебели.
CREATE TABLE public.categories (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL,

    CONSTRAINT uq_categories_name UNIQUE (name),
    CONSTRAINT ck_categories_name
        CHECK (length(btrim(name)) > 0)
);

-- 5. Товары.
CREATE TABLE public.products (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category_id BIGINT NOT NULL,
    supplier_id BIGINT NOT NULL,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(14, 2) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_products_category
        FOREIGN KEY (category_id)
        REFERENCES public.categories (id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_products_supplier
        FOREIGN KEY (supplier_id)
        REFERENCES public.suppliers (id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_products_sku UNIQUE (sku),

    CONSTRAINT ck_products_sku
        CHECK (
            length(btrim(sku)) > 0
            AND sku = upper(btrim(sku))
        ),

    CONSTRAINT ck_products_name
        CHECK (length(btrim(name)) > 0),

    CONSTRAINT ck_products_price
        CHECK (
            price >= 0
            AND price <> 'NaN'::NUMERIC
        )
);

-- 6. Склады.
CREATE TABLE public.warehouses (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    address TEXT,

    CONSTRAINT uq_warehouses_name UNIQUE (name),
    CONSTRAINT ck_warehouses_name
        CHECK (length(btrim(name)) > 0)
);

-- 7. Пользователи приложения.
CREATE TABLE public.users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    login VARCHAR(100) NOT NULL,
    password_hash TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT uq_users_login UNIQUE (login),
    CONSTRAINT ck_users_login
        CHECK (length(btrim(login)) > 0),
    CONSTRAINT ck_users_password_hash
        CHECK (length(btrim(password_hash)) > 0)
);

-- 8. Прикладные роли.
CREATE TABLE public.roles (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(50) NOT NULL,

    CONSTRAINT uq_roles_name UNIQUE (name),
    CONSTRAINT ck_roles_name
        CHECK (length(btrim(name)) > 0)
);

-- 9. Назначение ролей пользователям.
CREATE TABLE public.user_roles (
    user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,

    CONSTRAINT pk_user_roles
        PRIMARY KEY (user_id, role_id),

    CONSTRAINT fk_user_roles_user
        FOREIGN KEY (user_id)
        REFERENCES public.users (id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_user_roles_role
        FOREIGN KEY (role_id)
        REFERENCES public.roles (id)
        ON DELETE RESTRICT
);

-- 10. Остатки товаров на складах.
CREATE TABLE public.stock_balances (
    warehouse_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    on_hand INTEGER NOT NULL DEFAULT 0,
    reserved INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT pk_stock_balances
        PRIMARY KEY (warehouse_id, product_id),

    CONSTRAINT fk_stock_warehouse
        FOREIGN KEY (warehouse_id)
        REFERENCES public.warehouses (id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_stock_product
        FOREIGN KEY (product_id)
        REFERENCES public.products (id)
        ON DELETE RESTRICT,

    CONSTRAINT ck_stock_on_hand
        CHECK (on_hand >= 0),

    CONSTRAINT ck_stock_reserved
        CHECK (reserved >= 0),

    CONSTRAINT ck_stock_reserved_within_on_hand
        CHECK (reserved <= on_hand)
);

-- Индексы для поиска по внешним ключам.
CREATE INDEX ix_contacts_customer
    ON public.customer_contacts (customer_id);

CREATE INDEX ix_products_category
    ON public.products (category_id);

CREATE INDEX ix_products_supplier
    ON public.products (supplier_id);

CREATE INDEX ix_user_roles_role
    ON public.user_roles (role_id);

CREATE INDEX ix_stock_product
    ON public.stock_balances (product_id);

COMMIT;