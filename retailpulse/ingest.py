"""Incremental load of UCI Online Retail II into PostgreSQL, as a SIMULATED feed.

The dataset ends in 2011, so "incremental" means replaying it: each run loads the next window of invoice time after
the last successful batch. Re-running a window loads nothing new (the table's unique key rejects repeats), so a
schedule can retry safely. Every batch, including a failed one, gets a row in uci.ingest_log.

    python -m retailpulse.ingest --days 7              # next week of history (what a cron job runs)
    python -m retailpulse.ingest --through 2011-12-09  # catch up to the end
"""
import argparse
import logging

import pandas as pd

from . import config, uci
from .db import connect
from .pipeline import _copy

log = logging.getLogger("retailpulse.ingest")

REQUIRED = ["invoice", "stock_code", "quantity", "invoice_ts", "price", "country"]
KEY = ["invoice", "stock_code", "description", "quantity", "invoice_ts", "price", "customer_id", "country"]


def setup() -> None:
    with connect() as conn:
        conn.execute((config.SQL_DIR / "03_uci.sql").read_text())


def watermark() -> pd.Timestamp | None:
    """End of the last successful batch; failed batches do not move it."""
    with connect() as conn:
        end = conn.execute("SELECT max(window_end) FROM uci.ingest_log WHERE status = 'ok'").fetchone()[0]
    return pd.Timestamp(end) if end else None


def load_window(df: pd.DataFrame, end: pd.Timestamp) -> dict:
    """Load normalized rows with watermark < invoice_ts <= end in one transaction and log the outcome."""
    start = watermark()
    window = df[(df["invoice_ts"] <= end) & ((df["invoice_ts"] > start) if start is not None else True)]
    valid = window.dropna(subset=REQUIRED)
    stats = {"window_start": start, "window_end": end, "rows_in": len(window),
             "rows_rejected": len(window) - len(valid)}
    try:
        with connect() as conn, conn.transaction():
            batch = conn.execute("SELECT nextval('uci.ingest_log_batch_id_seq')").fetchone()[0]
            conn.execute("CREATE TEMP TABLE incoming (LIKE uci.lines) ON COMMIT DROP")
            _copy(conn, "incoming", valid[KEY].assign(batch_id=batch))
            new = conn.execute(f"INSERT INTO uci.lines SELECT * FROM incoming "
                               f"ON CONFLICT ON CONSTRAINT lines_no_duplicates DO NOTHING").rowcount
            stats |= {"rows_new": new, "rows_duplicate": len(valid) - new}
            conn.execute("INSERT INTO uci.ingest_log (batch_id, window_start, window_end, rows_in, rows_rejected, "
                         "rows_duplicate, rows_new, status) VALUES (%s, %s, %s, %s, %s, %s, %s, 'ok')",
                         (batch, start, end, stats["rows_in"], stats["rows_rejected"], stats["rows_duplicate"], new))
    except Exception as e:
        with connect() as conn:
            conn.execute("INSERT INTO uci.ingest_log (window_start, window_end, rows_in, rows_rejected, status, error)"
                         " VALUES (%s, %s, %s, %s, 'failed', %s)",
                         (start, end, stats["rows_in"], stats["rows_rejected"], f"{type(e).__name__}: {e}"[:500]))
        log.exception("batch up to %s failed; nothing from it was kept", end)
        raise
    log.info("batch %s: %s", batch, stats)
    return stats


def run(days: int | None = None, through: str | None = None) -> dict:
    setup()
    raw = uci.read()
    uci.validate(raw)
    df = uci.normalize(raw)
    start = watermark()
    if through:
        end = pd.Timestamp(through) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)   # through = whole day
    else:
        end = (start if start is not None else df["invoice_ts"].min().normalize() - pd.Timedelta(seconds=1)) \
            + pd.Timedelta(days=days or 7)
    return load_window(df, end)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--days", type=int, help="load this many days after the last batch (default 7)")
    g.add_argument("--through", help="load everything up to and including this date (YYYY-MM-DD)")
    a = p.parse_args()
    run(a.days, a.through)
