-- Analytical views. Each one is a Tableau data source (exported to data/tableau/ by retailpulse.extracts).
-- Metric definitions:
--   revenue        = sum(sales)                       (net of discount, as recorded)
--   profit         = sum(profit)                      (as recorded)
--   margin_pct     = 100 * profit / revenue
--   aov            = revenue / distinct orders
--   discount_rate  = discount_amount / gross_sales    (revenue-weighted, not the average of line discounts)
DROP VIEW IF EXISTS analytics.sales_wide, analytics.yearly_kpis, analytics.monthly_trends,
    analytics.product_performance, analytics.subcategory_margin, analytics.regional_performance,
    analytics.discount_bands, analytics.margin_bridge, analytics.customer_rfm, analytics.cohort_retention,
    analytics.segment_summary, analytics.returns_summary CASCADE;

-- One wide, denormalized row per line: the main Tableau extract (LODs and table calcs run on top of it).
CREATE VIEW analytics.sales_wide AS
SELECT f.row_id, f.order_id, f.order_date, f.ship_date, f.days_to_ship, f.ship_mode,
       c.customer_id, c.customer_name, c.segment,
       g.country, g.region, g.state, g.city, g.postal_code, g.regional_manager,
       p.product_id, p.product_name, p.category, p.sub_category,
       f.quantity, f.discount, f.gross_sales, f.discount_amount, f.sales, f.profit, f.implied_cost,
       f.is_returned
FROM mart.fct_sales f
JOIN mart.dim_customer c USING (customer_id)
JOIN mart.dim_product p USING (product_key)
JOIN mart.dim_geography g USING (geo_key);

CREATE VIEW analytics.yearly_kpis AS
WITH y AS (
    SELECT extract(year FROM order_date)::int AS year,
           sum(sales) AS revenue, sum(profit) AS profit, count(*) AS orders,
           count(DISTINCT customer_id) AS customers,
           sum(discount_amount) AS discount_amount, sum(gross_sales) AS gross_sales,
           count(*) FILTER (WHERE profit < 0) AS loss_orders
    FROM mart.fct_orders GROUP BY 1
)
SELECT year, round(revenue, 2) AS revenue, round(profit, 2) AS profit,
       round(100 * profit / revenue, 2)                                       AS margin_pct,
       orders, customers, round(revenue / orders, 2)                          AS aov,
       round(100 * discount_amount / gross_sales, 2)                          AS discount_rate_pct,
       round(100.0 * loss_orders / orders, 2)                                 AS loss_order_pct,
       round(100 * (revenue / lag(revenue) OVER w - 1), 2)                    AS revenue_yoy_pct,
       round(100 * (profit / lag(profit) OVER w - 1), 2)                      AS profit_yoy_pct,
       round(100 * profit / revenue - lag(100 * profit / revenue) OVER w, 2)  AS margin_change_pp
FROM y WINDOW w AS (ORDER BY year);

CREATE VIEW analytics.monthly_trends AS
WITH m AS (
    SELECT date_trunc('month', order_date)::date AS month,
           sum(sales) AS revenue, sum(profit) AS profit, count(*) AS orders
    FROM mart.fct_orders GROUP BY 1
)
SELECT month, round(revenue, 2) AS revenue, round(profit, 2) AS profit, orders,
       round(100 * profit / revenue, 2)                                              AS margin_pct,
       round(avg(revenue) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS revenue_rolling_3m,
       round(100 * sum(profit) OVER r12 / sum(revenue) OVER r12, 2)                  AS margin_rolling_12m_pct,
       round(100 * (revenue / lag(revenue, 12) OVER (ORDER BY month) - 1), 2)        AS revenue_yoy_pct,
       round(100 * (profit / nullif(lag(profit, 12) OVER (ORDER BY month), 0) - 1), 2) AS profit_yoy_pct
FROM m WINDOW r12 AS (ORDER BY month ROWS BETWEEN 11 PRECEDING AND CURRENT ROW);

CREATE VIEW analytics.product_performance AS
WITH p AS (
    SELECT p.product_key, p.product_id, p.product_name, p.category, p.sub_category,
           sum(f.sales) AS revenue, sum(f.profit) AS profit, sum(f.quantity) AS units,
           count(DISTINCT f.order_id) AS orders,
           sum(f.discount_amount) / sum(f.gross_sales) AS discount_rate
    FROM mart.fct_sales f JOIN mart.dim_product p USING (product_key)
    GROUP BY 1, 2, 3, 4, 5
), ranked AS (
    SELECT p.*,
           dense_rank() OVER (ORDER BY revenue DESC)                              AS revenue_rank,
           dense_rank() OVER (ORDER BY profit DESC)                               AS profit_rank,
           dense_rank() OVER (ORDER BY profit)                                    AS loss_rank,
           dense_rank() OVER (PARTITION BY sub_category ORDER BY profit DESC)     AS profit_rank_in_sub_category,
           sum(revenue) OVER (ORDER BY revenue DESC, product_key) / sum(revenue) OVER () AS cum_revenue_share
    FROM p
)
SELECT product_key, product_id, product_name, category, sub_category,
       round(revenue, 2) AS revenue, round(profit, 2) AS profit,
       round(100 * profit / revenue, 2) AS margin_pct, units, orders,
       round(100 * discount_rate, 2) AS discount_rate_pct,
       revenue_rank, profit_rank, loss_rank, profit_rank_in_sub_category,
       round(100 * cum_revenue_share, 2) AS cum_revenue_share_pct,
       CASE WHEN cum_revenue_share <= 0.8 THEN 'A' WHEN cum_revenue_share <= 0.95 THEN 'B' ELSE 'C' END AS abc_class,
       profit < 0 AS is_unprofitable
FROM ranked;

CREATE VIEW analytics.subcategory_margin AS
WITH s AS (
    SELECT p.category, p.sub_category, extract(year FROM f.order_date)::int AS year,
           sum(f.sales) AS revenue, sum(f.profit) AS profit,
           sum(f.discount_amount) / sum(f.gross_sales) AS discount_rate
    FROM mart.fct_sales f JOIN mart.dim_product p USING (product_key)
    GROUP BY 1, 2, 3
)
SELECT category, sub_category, year, round(revenue, 2) AS revenue, round(profit, 2) AS profit,
       round(100 * profit / revenue, 2) AS margin_pct,
       round(100 * discount_rate, 2) AS discount_rate_pct,
       round(100 * profit / revenue - lag(100 * profit / revenue) OVER w, 2) AS margin_change_pp,
       round(100 * revenue / sum(revenue) OVER (PARTITION BY year), 2) AS revenue_share_pct
FROM s WINDOW w AS (PARTITION BY category, sub_category ORDER BY year);

CREATE VIEW analytics.regional_performance AS
WITH r AS (
    SELECT g.region, g.state, g.regional_manager, extract(year FROM f.order_date)::int AS year,
           sum(f.sales) AS revenue, sum(f.profit) AS profit,
           sum(f.discount_amount) / sum(f.gross_sales) AS discount_rate
    FROM mart.fct_sales f JOIN mart.dim_geography g USING (geo_key)
    GROUP BY 1, 2, 3, 4
)
SELECT region, state, regional_manager, year, round(revenue, 2) AS revenue, round(profit, 2) AS profit,
       round(100 * profit / revenue, 2) AS margin_pct,
       round(100 * discount_rate, 2) AS discount_rate_pct,
       round(100 * revenue / sum(revenue) OVER (PARTITION BY year), 2)          AS revenue_share_pct,
       round(100 * profit / sum(profit) OVER (PARTITION BY year), 2)            AS profit_share_pct,
       dense_rank() OVER (PARTITION BY year ORDER BY profit)                    AS loss_rank
FROM r;

CREATE VIEW analytics.discount_bands AS
SELECT CASE WHEN discount = 0 THEN '0%' WHEN discount <= 0.2 THEN '1-20%'
            WHEN discount <= 0.4 THEN '21-40%' ELSE '41-80%' END                AS discount_band,
       count(*)                                                                 AS lines,
       round(sum(sales), 2)                                                     AS revenue,
       round(sum(profit), 2)                                                    AS profit,
       round(100 * sum(profit) / sum(sales), 2)                                 AS margin_pct,
       round(100.0 * count(*) FILTER (WHERE profit < 0) / count(*), 2)          AS loss_line_pct,
       round(100 * sum(sales) / sum(sum(sales)) OVER (), 2)                     AS revenue_share_pct
FROM mart.fct_sales GROUP BY 1;

-- Year-over-year margin change split into a mix effect (revenue moving between sub-categories with
-- different margins) and a rate effect (margins changing within a sub-category). The two add up exactly.
CREATE VIEW analytics.margin_bridge AS
WITH s AS (
    SELECT p.sub_category, extract(year FROM f.order_date)::int AS year,
           sum(f.sales) AS revenue, sum(f.profit) AS profit
    FROM mart.fct_sales f JOIN mart.dim_product p USING (product_key) GROUP BY 1, 2
), shares AS (
    SELECT sub_category, year, revenue / sum(revenue) OVER (PARTITION BY year) AS share,
           profit / revenue AS margin
    FROM s
), pairs AS (
    SELECT cur.year, cur.sub_category,
           coalesce(prev.share, 0) AS share_prev, cur.share AS share_cur,
           coalesce(prev.margin, cur.margin) AS margin_prev, cur.margin AS margin_cur
    FROM shares cur LEFT JOIN shares prev ON prev.sub_category = cur.sub_category AND prev.year = cur.year - 1
    WHERE cur.year > (SELECT min(year) FROM shares)
)
SELECT year, sub_category,
       round(100 * (share_cur - share_prev) * margin_prev, 3)  AS mix_effect_pp,
       round(100 * share_cur * (margin_cur - margin_prev), 3)  AS rate_effect_pp,
       round(100 * share_cur, 2)                                AS revenue_share_pct,
       round(100 * margin_cur, 2)                               AS margin_pct,
       round(100 * margin_prev, 2)                              AS margin_prev_pct
FROM pairs;

CREATE VIEW analytics.customer_rfm AS
WITH c AS (
    SELECT customer_id,
           (SELECT max(order_date) FROM mart.fct_orders) - max(order_date) AS recency_days,
           count(*) AS frequency, sum(sales) AS monetary, sum(profit) AS profit,
           min(order_date) AS first_order, max(order_date) AS last_order
    FROM mart.fct_orders GROUP BY customer_id
), scored AS (
    SELECT c.*,
           ntile(5) OVER (ORDER BY recency_days DESC) AS r,
           ntile(5) OVER (ORDER BY frequency)         AS f,
           ntile(5) OVER (ORDER BY monetary)          AS m
    FROM c
)
SELECT s.customer_id, d.customer_name, d.segment, s.recency_days, s.frequency,
       round(s.monetary, 2) AS monetary, round(s.profit, 2) AS profit, s.first_order, s.last_order,
       s.r, s.f, s.m, concat(s.r, s.f, s.m) AS rfm_code,
       CASE WHEN s.r >= 4 AND s.f >= 4 AND s.m >= 4 THEN 'Champions'
            WHEN s.r >= 3 AND s.f >= 3                THEN 'Loyal'
            WHEN s.r >= 4 AND s.f <= 2                THEN 'Recent, low frequency'
            WHEN s.r <= 2 AND s.f >= 3 AND s.m >= 3   THEN 'At risk, high value'
            WHEN s.r <= 2                             THEN 'Lapsing'
            ELSE 'Needs attention' END AS rfm_segment
FROM scored s JOIN mart.dim_customer d USING (customer_id);

-- Quarterly cohorts: share of each first-purchase cohort that ordered again N quarters later.
CREATE VIEW analytics.cohort_retention AS
WITH firsts AS (
    SELECT customer_id, date_trunc('quarter', min(order_date))::date AS cohort_quarter
    FROM mart.fct_orders GROUP BY customer_id
), activity AS (
    SELECT DISTINCT o.customer_id, f.cohort_quarter,
           ((extract(year FROM o.order_date) - extract(year FROM f.cohort_quarter)) * 4
            + extract(quarter FROM o.order_date) - extract(quarter FROM f.cohort_quarter))::int AS quarters_since_first
    FROM mart.fct_orders o JOIN firsts f USING (customer_id)
), counts AS (
    SELECT cohort_quarter, quarters_since_first, count(*) AS active_customers
    FROM activity GROUP BY 1, 2
)
SELECT cohort_quarter, quarters_since_first, active_customers,
       first_value(active_customers) OVER (PARTITION BY cohort_quarter ORDER BY quarters_since_first) AS cohort_size,
       round(100.0 * active_customers
             / first_value(active_customers) OVER (PARTITION BY cohort_quarter ORDER BY quarters_since_first), 2)
           AS retention_pct
FROM counts;

CREATE VIEW analytics.segment_summary AS
WITH s AS (
    SELECT d.segment, extract(year FROM o.order_date)::int AS year,
           count(DISTINCT o.customer_id) AS customers, count(*) AS orders,
           sum(o.sales) AS revenue, sum(o.profit) AS profit
    FROM mart.fct_orders o JOIN mart.dim_customer d USING (customer_id)
    GROUP BY 1, 2
)
SELECT segment, year, customers, orders, round(revenue, 2) AS revenue, round(profit, 2) AS profit,
       round(100 * profit / revenue, 2) AS margin_pct, round(revenue / orders, 2) AS aov,
       round(100 * revenue / sum(revenue) OVER (PARTITION BY year), 2) AS revenue_share_pct
FROM s;

CREATE VIEW analytics.returns_summary AS
SELECT g.region, p.category,
       count(DISTINCT f.order_id)                                               AS orders,
       count(DISTINCT f.order_id) FILTER (WHERE f.is_returned)                  AS returned_orders,
       round(100.0 * count(DISTINCT f.order_id) FILTER (WHERE f.is_returned)
             / count(DISTINCT f.order_id), 2)                                   AS return_rate_pct,
       round(sum(f.sales) FILTER (WHERE f.is_returned), 2)                      AS returned_revenue
FROM mart.fct_sales f
JOIN mart.dim_geography g USING (geo_key)
JOIN mart.dim_product p USING (product_key)
GROUP BY 1, 2;
