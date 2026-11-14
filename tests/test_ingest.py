import pandas as pd
import pytest

from retailpulse import ingest
from retailpulse.db import query


def lines(rows):
    """(invoice, stock code, qty, timestamp, price, customer) -> normalized UCI rows."""
    df = pd.DataFrame(rows, columns=["invoice", "stock_code", "quantity", "invoice_ts", "price", "customer_id"])
    return df.assign(description="ITEM", country="United Kingdom", invoice_ts=pd.to_datetime(df["invoice_ts"]),
                     customer_id=df["customer_id"].astype("string"))


DAY1 = pd.Timestamp("2010-01-04 23:59:59")
DAY2 = pd.Timestamp("2010-01-05 23:59:59")
SALE = ("500001", "85048", 2, "2010-01-04 10:00", 5.0, "1")
ROWS = lines([SALE, SALE,                                       # exact repeat: the source's duplicate pattern
              ("500002", "POST", 1, "2010-01-04 11:00", 18.0, "1"),   # postage, not product revenue
              ("C500003", "85048", -1, "2010-01-04 12:00", 5.0, "1"),  # cancellation, netted
              ("500004", "22423", 1, "2010-01-05 09:00", 12.5, None)])


def test_repeated_lines_and_reruns_are_loaded_once(uci_db):
    first = ingest.load_window(ROWS, DAY1)
    assert (first["rows_in"], first["rows_new"], first["rows_duplicate"]) == (4, 3, 1)
    # a scheduler retrying the same window: the watermark has moved past it, so nothing is even read
    again = ingest.load_window(ROWS, DAY1)
    assert again["rows_in"] == 0
    assert query("SELECT count(*) AS n FROM uci.lines")["n"][0] == 3


def test_each_run_picks_up_after_the_last_successful_batch(uci_db):
    ingest.load_window(ROWS, DAY1)
    second = ingest.load_window(ROWS, DAY2)
    assert second["window_start"] == DAY1 and second["rows_new"] == 1


def test_rows_missing_required_fields_are_counted_not_loaded(uci_db):
    bad = pd.concat([ROWS.head(1), lines([(None, "85048", 1, "2010-01-04 13:00", 5.0, "2")])])
    out = ingest.load_window(bad, DAY1)
    assert (out["rows_rejected"], out["rows_new"]) == (1, 1)


def test_a_failed_batch_keeps_nothing_and_does_not_move_the_watermark(uci_db):
    broken = ROWS.assign(quantity=ROWS["quantity"].astype(float) + 0.5)    # not an integer: COPY fails
    with pytest.raises(Exception):
        ingest.load_window(broken, DAY1)
    logged = query("SELECT status, error FROM uci.ingest_log")
    assert list(logged["status"]) == ["failed"] and logged["error"][0]
    assert query("SELECT count(*) AS n FROM uci.lines")["n"][0] == 0
    assert ingest.watermark() is None


def test_daily_revenue_nets_cancellations_and_leaves_out_postage(uci_db):
    ingest.load_window(ROWS, DAY2)
    day = query("SELECT * FROM uci.daily_sales ORDER BY day").set_index("day")
    jan4 = day.loc[pd.Timestamp("2010-01-04").date()]
    assert float(jan4["gross_revenue"]) == 10.0          # one 2 x 5.00 sale; the duplicate and postage excluded
    assert float(jan4["cancelled_revenue"]) == -5.0
    assert float(jan4["net_revenue"]) == 5.0
    assert jan4["invoices"] == 1
