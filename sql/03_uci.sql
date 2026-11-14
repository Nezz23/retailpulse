-- UCI Online Retail II: real transactions, loaded incrementally by retailpulse/ingest.py. Kept apart from the
-- Superstore marts (which are rebuilt on every run), so this file never drops data.
CREATE SCHEMA IF NOT EXISTS uci;

CREATE TABLE IF NOT EXISTS uci.lines (
    invoice     text             NOT NULL,
    stock_code  text             NOT NULL,
    description text,
    quantity    integer          NOT NULL,
    invoice_ts  timestamp        NOT NULL,
    price       double precision NOT NULL,
    customer_id text,
    country     text             NOT NULL,
    batch_id    integer          NOT NULL,
    -- the source has no line number, so an exact repeat of every field is the only duplicate test available
    CONSTRAINT lines_no_duplicates UNIQUE NULLS NOT DISTINCT
        (invoice, stock_code, description, quantity, invoice_ts, price, customer_id, country)
);

CREATE TABLE IF NOT EXISTS uci.ingest_log (
    batch_id       serial PRIMARY KEY,
    window_start   timestamp,
    window_end     timestamp NOT NULL,
    rows_in        integer,
    rows_rejected  integer,
    rows_duplicate integer,
    rows_new       integer,
    status         text NOT NULL CHECK (status IN ('ok', 'failed')),
    error          text,
    ran_at         timestamptz NOT NULL DEFAULT now()
);

-- Product revenue per day. Cancellations (C...) are netted in; bad-debt adjustments (A...), zero/negative prices
-- and non-product codes (postage, fees, manual lines) are left out. Product codes start with five digits.
CREATE OR REPLACE VIEW uci.daily_sales AS
SELECT invoice_ts::date                                                       AS day,
       round(sum(quantity * price) FILTER (WHERE invoice NOT LIKE 'C%')::numeric, 2) AS gross_revenue,
       round(coalesce(sum(quantity * price) FILTER (WHERE invoice LIKE 'C%'), 0)::numeric, 2) AS cancelled_revenue,
       round(sum(quantity * price)::numeric, 2)                                AS net_revenue,
       count(DISTINCT invoice) FILTER (WHERE invoice NOT LIKE 'C%')            AS invoices,
       count(DISTINCT customer_id) FILTER (WHERE invoice NOT LIKE 'C%')        AS customers
FROM uci.lines
WHERE stock_code ~ '^[0-9]{5}' AND price > 0 AND invoice NOT LIKE 'A%'
GROUP BY 1;
