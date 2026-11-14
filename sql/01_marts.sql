-- Star schema. Rebuilt from staging on every run.
--   grain of mart.fct_sales: one product line of one order (Row ID)
--   grain of mart.fct_orders: one order
DROP TABLE IF EXISTS mart.fct_sales, mart.fct_orders, mart.dim_customer, mart.dim_product,
                     mart.dim_geography, mart.dim_date CASCADE;

CREATE TABLE mart.dim_date AS
SELECT d::date                               AS date,
       extract(year FROM d)::int             AS year,
       extract(quarter FROM d)::int          AS quarter,
       extract(month FROM d)::int            AS month,
       to_char(d, 'Mon')                     AS month_name,
       date_trunc('month', d)::date          AS month_start,
       date_trunc('quarter', d)::date        AS quarter_start,
       extract(isodow FROM d)::int           AS iso_weekday,
       extract(isodow FROM d) IN (6, 7)      AS is_weekend
FROM generate_series((SELECT date_trunc('year', min(order_date)) FROM staging.orders),
                     (SELECT date_trunc('year', max(ship_date)) + interval '1 year - 1 day' FROM staging.orders),
                     interval '1 day') AS d;
ALTER TABLE mart.dim_date ADD PRIMARY KEY (date);

-- Customer attributes never conflict in the source (checked in the profile), so one row per customer.
CREATE TABLE mart.dim_customer AS
SELECT customer_id, min(customer_name) AS customer_name, min(segment) AS segment
FROM staging.orders GROUP BY customer_id;
ALTER TABLE mart.dim_customer ADD PRIMARY KEY (customer_id);

-- The source reuses 32 Product IDs for different product names, so the product key is surrogate
-- over (product_id, product_name) rather than the Product ID alone.
CREATE TABLE mart.dim_product AS
SELECT row_number() OVER (ORDER BY product_id, product_name)::int AS product_key,
       product_id, product_name, category, sub_category
FROM (SELECT DISTINCT product_id, product_name, category, sub_category FROM staging.orders) p;
ALTER TABLE mart.dim_product ADD PRIMARY KEY (product_key);
ALTER TABLE mart.dim_product ADD UNIQUE (product_id, product_name);

CREATE TABLE mart.dim_geography AS
SELECT row_number() OVER (ORDER BY country, region, state, city, postal_code)::int AS geo_key,
       g.country, g.region, g.state, g.city, g.postal_code, p.regional_manager
FROM (SELECT DISTINCT country, region, state, city, postal_code FROM staging.orders) g
LEFT JOIN staging.people p USING (region);
ALTER TABLE mart.dim_geography ADD PRIMARY KEY (geo_key);

-- implied_cost = sales - profit is derived from the two recorded fields, not an independent cost source.
CREATE TABLE mart.fct_sales AS
SELECT o.row_id,
       o.order_id,
       o.order_date,
       o.ship_date,
       o.customer_id,
       p.product_key,
       g.geo_key,
       o.ship_mode,
       o.quantity,
       o.discount,
       o.sales,
       round(o.sales / (1 - o.discount), 4)            AS gross_sales,
       round(o.sales / (1 - o.discount) - o.sales, 4)  AS discount_amount,
       o.profit,
       o.sales - o.profit                              AS implied_cost,
       (o.ship_date - o.order_date)                    AS days_to_ship,
       r.order_id IS NOT NULL                          AS is_returned
FROM staging.orders o
JOIN mart.dim_product p USING (product_id, product_name)
JOIN mart.dim_geography g ON g.country = o.country AND g.region = o.region AND g.state = o.state
                         AND g.city = o.city AND g.postal_code IS NOT DISTINCT FROM o.postal_code
LEFT JOIN staging.returns r USING (order_id);
ALTER TABLE mart.fct_sales ADD PRIMARY KEY (row_id);
ALTER TABLE mart.fct_sales ADD FOREIGN KEY (order_date) REFERENCES mart.dim_date (date);
ALTER TABLE mart.fct_sales ADD FOREIGN KEY (ship_date) REFERENCES mart.dim_date (date);
ALTER TABLE mart.fct_sales ADD FOREIGN KEY (customer_id) REFERENCES mart.dim_customer (customer_id);
ALTER TABLE mart.fct_sales ADD FOREIGN KEY (product_key) REFERENCES mart.dim_product (product_key);
ALTER TABLE mart.fct_sales ADD FOREIGN KEY (geo_key) REFERENCES mart.dim_geography (geo_key);
CREATE INDEX ON mart.fct_sales (order_date);
CREATE INDEX ON mart.fct_sales (customer_id);
CREATE INDEX ON mart.fct_sales (product_key);
CREATE INDEX ON mart.fct_sales (order_id);

-- Two source orders carry two customer IDs; the order is attributed to the customer with the most sales.
CREATE TABLE mart.fct_orders AS
WITH by_customer AS (
    SELECT order_id, customer_id, sum(sales) AS s,
           row_number() OVER (PARTITION BY order_id ORDER BY sum(sales) DESC, customer_id) AS rn
    FROM mart.fct_sales GROUP BY order_id, customer_id
)
SELECT f.order_id,
       min(f.order_date)                 AS order_date,
       max(f.ship_date)                  AS ship_date,
       c.customer_id,
       min(f.ship_mode)                  AS ship_mode,
       count(*)                          AS lines,
       sum(f.quantity)                   AS units,
       sum(f.sales)                      AS sales,
       sum(f.gross_sales)                AS gross_sales,
       sum(f.discount_amount)            AS discount_amount,
       sum(f.profit)                     AS profit,
       bool_or(f.discount > 0)           AS has_discount,
       bool_or(f.is_returned)            AS is_returned
FROM mart.fct_sales f
JOIN by_customer c ON c.order_id = f.order_id AND c.rn = 1
GROUP BY f.order_id, c.customer_id;
ALTER TABLE mart.fct_orders ADD PRIMARY KEY (order_id);
ALTER TABLE mart.fct_orders ADD FOREIGN KEY (customer_id) REFERENCES mart.dim_customer (customer_id);
CREATE INDEX ON mart.fct_orders (order_date);
