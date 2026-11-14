"""Ingest Tableau's Sample Superstore into PostgreSQL, then build the star schema and analytical views.

Steps: download -> read 3 sheets -> validate schema -> profile -> normalize (dates, keys, duplicates) ->
business-rule checks -> COPY into staging -> run sql/*.sql -> data-quality assertions on the marts.
Every step logs counts so nothing is dropped silently."""
import argparse
import io
import json
import logging
import urllib.request

import pandas as pd

from . import config
from .db import connect, run_sql_dir

log = logging.getLogger("retailpulse.pipeline")

ORDER_COLUMNS = {
    "Row ID": "row_id", "Order ID": "order_id", "Order Date": "order_date", "Ship Date": "ship_date",
    "Ship Mode": "ship_mode", "Customer ID": "customer_id", "Customer Name": "customer_name",
    "Segment": "segment", "Country/Region": "country", "City": "city", "State/Province": "state",
    "Postal Code": "postal_code", "Region": "region", "Product ID": "product_id", "Category": "category",
    "Sub-Category": "sub_category", "Product Name": "product_name", "Sales": "sales", "Quantity": "quantity",
    "Discount": "discount", "Profit": "profit",
}
NUMERIC = ("Row ID", "Sales", "Quantity", "Discount", "Profit")
DATES = ("Order Date", "Ship Date")


class SchemaError(ValueError):
    pass


def download() -> None:
    config.RAW_XLS.parent.mkdir(parents=True, exist_ok=True)
    log.info("downloading %s", config.SOURCE_URL)
    urllib.request.urlretrieve(config.SOURCE_URL, config.RAW_XLS)


def read_source() -> dict[str, pd.DataFrame]:
    if not config.RAW_XLS.exists():
        download()
    return pd.read_excel(config.RAW_XLS, sheet_name=["Orders", "Returns", "People"],
                         dtype={"Postal Code": str, "Order ID": str})


def validate(sheets: dict[str, pd.DataFrame]) -> None:
    orders = sheets["Orders"]
    missing = set(ORDER_COLUMNS) - set(orders.columns)
    if missing:
        raise SchemaError(f"Orders is missing columns: {sorted(missing)}")
    for col in NUMERIC:
        if not pd.api.types.is_numeric_dtype(orders[col]):
            raise SchemaError(f"{col} must be numeric, got {orders[col].dtype}")
    for col in DATES:
        if not pd.api.types.is_datetime64_any_dtype(orders[col]):
            raise SchemaError(f"{col} must be a date, got {orders[col].dtype}")
    if not {"Order ID", "Returned"} <= set(sheets["Returns"].columns):
        raise SchemaError("Returns needs Order ID and Returned")
    if not {"Regional Manager", "Region"} <= set(sheets["People"].columns):
        raise SchemaError("People needs Regional Manager and Region")


def profile(orders: pd.DataFrame) -> dict:
    """Shape, nulls, duplicates and key anomalies of the raw Orders sheet."""
    o = orders
    return {
        "rows": len(o),
        "columns": len(o.columns),
        "order_date_range": [str(o["Order Date"].min().date()), str(o["Order Date"].max().date())],
        "missing_values": {k: int(v) for k, v in o.isna().sum().items() if v},
        "duplicate_row_ids": int(o["Row ID"].duplicated().sum()),
        "exact_duplicate_lines": int(o.drop(columns="Row ID").duplicated().sum()),
        "orders": int(o["Order ID"].nunique()),
        "customers": int(o["Customer ID"].nunique()),
        "product_ids": int(o["Product ID"].nunique()),
        "product_ids_with_several_names": int((o.groupby("Product ID")["Product Name"].nunique() > 1).sum()),
        "orders_with_several_customers": int((o.groupby("Order ID")["Customer ID"].nunique() > 1).sum()),
        "loss_making_lines": int((o["Profit"] < 0).sum()),
        "discount_levels": sorted(float(d) for d in o["Discount"].unique()),
    }


def normalize(sheets: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Snake-case columns, trimmed text, dates as dates, exact duplicate lines removed (first Row ID kept)."""
    o = sheets["Orders"].rename(columns=ORDER_COLUMNS)[list(ORDER_COLUMNS.values())].copy()
    for col in o.select_dtypes(include=["object", "string"]).columns:
        o[col] = o[col].astype(str).str.strip()
    o["order_date"] = pd.to_datetime(o["order_date"]).dt.date
    o["ship_date"] = pd.to_datetime(o["ship_date"]).dt.date
    o["postal_code"] = o["postal_code"].str.replace(r"\.0$", "", regex=True)
    before = len(o)
    o = o.drop_duplicates(subset=[c for c in o.columns if c != "row_id"], keep="first").reset_index(drop=True)
    returns = sheets["Returns"].rename(columns={"Order ID": "order_id", "Returned": "returned"})
    returns = returns[returns["returned"].str.strip().str.lower() == "yes"][["order_id"]].drop_duplicates()
    people = sheets["People"].rename(columns={"Regional Manager": "regional_manager", "Region": "region"})
    return o, returns, people, {"exact_duplicates_removed": before - len(o), "rows_out": len(o)}


def business_rules(o: pd.DataFrame) -> dict[str, int]:
    """Counts of rows that break a business rule. All must be zero to load."""
    implied_cost = o["sales"] - o["profit"]
    return {
        "ship date before order date": int((o["ship_date"] < o["order_date"]).sum()),
        "non-positive sales": int((o["sales"] <= 0).sum()),
        "non-positive quantity": int((o["quantity"] <= 0).sum()),
        "discount outside [0, 1)": int(((o["discount"] < 0) | (o["discount"] >= 1)).sum()),
        "negative implied cost (profit above sales)": int((implied_cost < 0).sum()),
    }


def _copy(conn, table: str, df: pd.DataFrame) -> None:
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    buf.seek(0)
    with conn.cursor().copy(f"COPY {table} ({', '.join(df.columns)}) FROM STDIN WITH (FORMAT csv)") as cp:
        cp.write(buf.read())


def load(o: pd.DataFrame, returns: pd.DataFrame, people: pd.DataFrame) -> None:
    """Full reload of staging (the source is a single static file, so there is nothing to append)."""
    with connect() as conn:
        conn.execute((config.SQL_DIR / "00_staging.sql").read_text())
        conn.execute("TRUNCATE staging.orders, staging.returns, staging.people")
        _copy(conn, "staging.orders", o)
        _copy(conn, "staging.returns", returns)
        _copy(conn, "staging.people", people)


QUALITY_CHECKS = {
    "fact rows reconcile to staging": "SELECT (SELECT count(*) FROM mart.fct_sales) = (SELECT count(*) FROM staging.orders)",
    "sales reconcile to staging": "SELECT abs((SELECT sum(sales) FROM mart.fct_sales) - (SELECT sum(sales) FROM staging.orders)) < 0.01",
    "profit reconciles to staging": "SELECT abs((SELECT sum(profit) FROM mart.fct_sales) - (SELECT sum(profit) FROM staging.orders)) < 0.01",
    "every order date is in dim_date": "SELECT count(*) = 0 FROM mart.fct_sales f LEFT JOIN mart.dim_date d ON d.date = f.order_date WHERE d.date IS NULL",
    "every region has a manager": "SELECT count(*) = 0 FROM mart.dim_geography g LEFT JOIN staging.people p USING (region) WHERE p.region IS NULL",
    "gross sales = sales + discount amount": "SELECT abs(sum(gross_sales) - sum(sales) - sum(discount_amount)) < 0.01 FROM mart.fct_sales",
    "order totals equal line totals": "SELECT abs((SELECT sum(sales) FROM mart.fct_orders) - (SELECT sum(sales) FROM mart.fct_sales)) < 0.01",
}


def quality_checks() -> dict[str, bool]:
    with connect() as conn:
        out = {name: bool(conn.execute(q).fetchone()[0]) for name, q in QUALITY_CHECKS.items()}
    failed = [k for k, ok in out.items() if not ok]
    if failed:
        raise AssertionError(f"data quality checks failed: {failed}")
    return out


def run() -> dict:
    sheets = read_source()
    validate(sheets)
    report = {"profile": profile(sheets["Orders"])}
    o, returns, people, stats = normalize(sheets)
    report["normalize"] = stats
    report["business_rule_violations"] = rules = business_rules(o)
    if any(rules.values()):
        raise AssertionError(f"business rules violated: {rules}")
    load(o, returns, people)
    run_sql_dir(config.SQL_DIR, skip=("00_staging.sql",))
    report["quality_checks"] = quality_checks()
    with connect() as conn:
        report["mart_counts"] = {t: conn.execute(f"SELECT count(*) FROM mart.{t}").fetchone()[0]
                                 for t in ("fct_sales", "fct_orders", "dim_customer", "dim_product",
                                           "dim_geography", "dim_date")}
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "data_quality.json").write_text(json.dumps(report, indent=2, default=str))
    log.info("pipeline done %s", report["mart_counts"])
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(run(), indent=2, default=str))
