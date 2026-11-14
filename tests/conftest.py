"""Tests run against a real PostgreSQL test database (CI provides one as a service container)."""
import os

import pandas as pd
import psycopg
import pytest

from retailpulse import config

TEST_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://localhost:5432/retailpulse_test")

# Hand-built lines covering the edge cases. Two years so YoY, cohorts and the margin bridge have values.
#  row, order, order date, ship date, customer, segment, region, state, product id, product name, category,
#  sub-category, sales, qty, discount, profit
ROWS = [
    (1, "O-1", "2025-01-10", "2025-01-12", "C1", "Consumer", "West", "California", "P1", "Chair", "Furniture", "Chairs", 100.0, 1, 0.0, 30.0),
    (2, "O-1", "2025-01-10", "2025-01-12", "C1", "Consumer", "West", "California", "P2", "Pen", "Office Supplies", "Art", 20.0, 2, 0.0, 10.0),
    (3, "O-2", "2025-02-05", "2025-02-08", "C2", "Corporate", "East", "New York", "P1", "Chair", "Furniture", "Chairs", 80.0, 1, 0.2, -10.0),
    (4, "O-3", "2026-01-15", "2026-01-16", "C1", "Consumer", "West", "California", "P1", "Chair", "Furniture", "Chairs", 200.0, 2, 0.0, 60.0),
    (5, "O-4", "2026-03-01", "2026-03-04", "C3", "Home Office", "East", "New York", "P2", "Pen", "Office Supplies", "Art", 40.0, 4, 0.5, -20.0),
    # P3 reuses one ID for two different products, as the real source does
    (6, "O-4", "2026-03-01", "2026-03-04", "C3", "Home Office", "East", "New York", "P3", "Desk", "Furniture", "Tables", 60.0, 1, 0.0, 12.0),
    (7, "O-5", "2026-03-02", "2026-03-04", "C2", "Corporate", "East", "New York", "P3", "Desk Lamp", "Furniture", "Tables", 30.0, 1, 0.0, -6.0),
    # O-6 has lines from two customers (another real-source quirk); C4 has the larger share
    (8, "O-6", "2026-04-01", "2026-04-02", "C4", "Consumer", "West", "Oregon", "P2", "Pen", "Office Supplies", "Art", 50.0, 5, 0.0, 25.0),
    (9, "O-6", "2026-04-01", "2026-04-02", "C5", "Consumer", "West", "Oregon", "P2", "Pen", "Office Supplies", "Art", 10.0, 1, 0.0, 5.0),
    # exact duplicate of row 2 apart from the Row ID
    (10, "O-1", "2025-01-10", "2025-01-12", "C1", "Consumer", "West", "California", "P2", "Pen", "Office Supplies", "Art", 20.0, 2, 0.0, 10.0),
]


def sheets(rows=ROWS) -> dict[str, pd.DataFrame]:
    orders = pd.DataFrame({
        "Row ID": [r[0] for r in rows], "Order ID": [r[1] for r in rows],
        "Order Date": pd.to_datetime([r[2] for r in rows]), "Ship Date": pd.to_datetime([r[3] for r in rows]),
        "Ship Mode": "Standard Class", "Customer ID": [r[4] for r in rows],
        "Customer Name": [f"Name {r[4]}" for r in rows], "Segment": [r[5] for r in rows],
        "Country/Region": "United States", "City": "Town", "State/Province": [r[7] for r in rows],
        "Postal Code": "01234", "Region": [r[6] for r in rows], "Product ID": [r[8] for r in rows],
        "Category": [r[10] for r in rows], "Sub-Category": [r[11] for r in rows],
        "Product Name": [r[9] for r in rows], "Sales": [r[12] for r in rows], "Quantity": [r[13] for r in rows],
        "Discount": [r[14] for r in rows], "Profit": [r[15] for r in rows]})
    returns = pd.DataFrame({"Order ID": ["O-2"], "Returned": ["Yes"]})
    people = pd.DataFrame({"Regional Manager": ["Ann", "Bo"], "Region": ["West", "East"]})
    return {"Orders": orders, "Returns": returns, "People": people}


@pytest.fixture
def db(monkeypatch):
    """Fresh, empty test database for each test."""
    admin = TEST_URL.rsplit("/", 1)[0] + "/postgres"
    name = TEST_URL.rsplit("/", 1)[1]
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        c.execute(f"CREATE DATABASE {name}")
    monkeypatch.setattr(config, "DATABASE_URL", TEST_URL)
    return TEST_URL


@pytest.fixture
def built(db):
    """The fixture rows pushed through the real pipeline: normalize, rules, load, SQL build."""
    from retailpulse import pipeline
    from retailpulse.db import run_sql_dir
    o, returns, people, stats = pipeline.normalize(sheets())
    pipeline.load(o, returns, people)
    run_sql_dir(config.SQL_DIR, skip=("00_staging.sql",))
    return stats


@pytest.fixture
def uci_db(db):
    """Empty test database with the UCI schema, log table and daily view."""
    from retailpulse import ingest
    ingest.setup()
    return db
