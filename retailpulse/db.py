"""PostgreSQL access."""
from pathlib import Path

import pandas as pd
import psycopg

from . import config


def connect() -> psycopg.Connection:
    return psycopg.connect(config.DATABASE_URL, autocommit=True)


def run_sql_dir(path: Path, skip: tuple[str, ...] = ()) -> None:
    """Run every .sql file in name order (00_, 01_, ...). Each file is idempotent (CREATE OR REPLACE / DROP)."""
    with connect() as conn:
        for f in sorted(path.glob("*.sql")):
            if f.name not in skip:
                conn.execute(f.read_text())


def query(sql: str, params: dict | tuple | None = None) -> pd.DataFrame:
    with connect() as conn:
        cur = conn.execute(sql, params)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
