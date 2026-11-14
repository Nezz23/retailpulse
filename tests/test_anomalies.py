import numpy as np
import pandas as pd

from retailpulse import anomalies, ingest
from tests.test_ingest import lines

MONTHS = pd.date_range("2023-01-01", "2026-12-01", freq="MS")   # four years, like the real data


def superstore_lines(spike: pd.Timestamp) -> pd.DataFrame:
    """One line per month: a repeating month pattern with small noise, 25% margin; one month tripled."""
    rng = np.random.default_rng(1)
    sales = 1000 * (1 + 0.5 * np.sin(MONTHS.month)) * rng.normal(1, 0.02, len(MONTHS))
    sales = np.where(MONTHS == spike, sales * 3, sales)
    return pd.DataFrame({"order_date": MONTHS, "sub_category": "Binders", "sales": sales, "profit": 0.25 * sales})


def test_a_spike_is_flagged_without_leaking_into_the_same_month_of_other_years():
    found = anomalies.superstore(superstore_lines(pd.Timestamp("2024-05-01")))
    may = {(a["metric"], a["period"]): a for a in found if a["period"].endswith("-05-01")}
    assert set(may) == {("revenue", "2024-05-01"), ("profit", "2024-05-01")}
    assert may[("revenue", "2024-05-01")]["severity"] == "severe" and may[("revenue", "2024-05-01")]["z"] > 0
    assert may[("revenue", "2024-05-01")]["context"]["vs"] == "2023-05-01"      # compared with the same month last year


def test_noise_alone_flags_under_one_percent_of_months():
    """Null calibration: month pattern + year level + heavy-tailed noise, no anomalies planted."""
    rng = np.random.default_rng(0)
    z = [anomalies.robust_z(x - anomalies.two_way_expected(x)).abs()
         for x in (pd.Series(np.tile(rng.normal(0, 5, 12), 4) + np.repeat(rng.normal(0, 3, 4), 12)
                             + rng.standard_t(5, 48), index=MONTHS) for _ in range(300))]
    assert (pd.concat(z) >= 4).mean() < 0.01


def test_severity_bands():
    assert [anomalies.severity(z) for z in (3.99, 4.0, -5.5, 6.0)] == [None, "moderate", "high", "severe"]


def test_a_spike_day_is_flagged_against_trailing_same_weekdays_only(uci_db):
    rng = np.random.default_rng(2)
    days = [d for d in pd.date_range("2010-02-01", "2010-07-31") if d.day_of_week != 5]
    spike = pd.Timestamp("2010-07-14")
    rows = [(str(i), "85048", 1, f"{d.date()} 10:00", round(float(rng.normal(1000, 30)) * (5 if d == spike else 1), 2), "1")
            for i, d in enumerate(days)]
    ingest.load_window(lines(rows), pd.Timestamp("2010-08-01"))
    found = anomalies.uci()
    assert [a["period"] for a in found] == ["2010-07-14"]
    assert 950 < found[0]["expected"] < 1050                       # the spike itself is not in its own baseline
    assert found[0]["context"]["invoices"] == 1 and found[0]["context"]["largest_invoice_share_pct"] == 100.0
