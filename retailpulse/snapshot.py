"""Small precomputed extracts from PostgreSQL, committed under results/snapshots/ so that the weekly report and the
Streamlit app run without a database (Streamlit Cloud, scheduled GitHub Actions)."""
from . import config
from .db import query

DIR = config.RESULTS_DIR / "snapshots"

QUERIES = {
    # Superstore (synthetic): one row per day
    "superstore_daily": """
        SELECT order_date AS day, round(sum(sales), 2) AS revenue, round(sum(profit), 2) AS profit,
               count(DISTINCT order_id) AS orders,
               round(coalesce(sum(sales) FILTER (WHERE discount > 0.2), 0), 2) AS deep_discount_revenue,
               round(coalesce(sum(profit) FILTER (WHERE discount > 0.2), 0), 2) AS deep_discount_profit
        FROM analytics.sales_wide GROUP BY 1 ORDER BY 1""",
    # Superstore latest-year lines: what the discount simulator reprices (scenarios.cap)
    "superstore_lines_latest": """
        SELECT category, sub_category, region, segment, discount, sales, profit, gross_sales, implied_cost
        FROM analytics.sales_wide
        WHERE extract(year FROM order_date) = (SELECT max(extract(year FROM order_date)) FROM analytics.sales_wide)""",
    # UCI Online Retail II (real): one row per trading day
    "uci_daily": "SELECT * FROM uci.daily_sales ORDER BY day",
    "uci_ingest_log": "SELECT * FROM uci.ingest_log ORDER BY batch_id",
}


def run() -> dict[str, int]:
    DIR.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, sql in QUERIES.items():
        df = query(sql)
        df.to_csv(DIR / f"{name}.csv", index=False)
        counts[name] = len(df)
    return counts


if __name__ == "__main__":
    print(run())
