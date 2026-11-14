-- Raw-but-typed landing tables. Loaded by retailpulse.pipeline with COPY (full reload each run).
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS staging.orders (
    row_id        integer PRIMARY KEY,
    order_id      text    NOT NULL,
    order_date    date    NOT NULL,
    ship_date     date    NOT NULL,
    ship_mode     text    NOT NULL,
    customer_id   text    NOT NULL,
    customer_name text    NOT NULL,
    segment       text    NOT NULL,
    country       text    NOT NULL,
    city          text    NOT NULL,
    state         text    NOT NULL,
    postal_code   text,
    region        text    NOT NULL,
    product_id    text    NOT NULL,
    category      text    NOT NULL,
    sub_category  text    NOT NULL,
    product_name  text    NOT NULL,
    sales         numeric(12, 4) NOT NULL CHECK (sales > 0),
    quantity      integer NOT NULL CHECK (quantity > 0),
    discount      numeric(4, 2)  NOT NULL CHECK (discount >= 0 AND discount < 1),
    profit        numeric(12, 4) NOT NULL
);
CREATE TABLE IF NOT EXISTS staging.returns (order_id text PRIMARY KEY);
CREATE TABLE IF NOT EXISTS staging.people (region text PRIMARY KEY, regional_manager text NOT NULL);
