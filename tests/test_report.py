import json

import pandas as pd
import pytest

from retailpulse import config, report, snapshot


@pytest.fixture
def results(tmp_path, monkeypatch):
    """A results/ folder with three weeks of UCI days (Mon 2011-01-03 .. Sun 01-23) and the JSON the report reads."""
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(snapshot, "DIR", tmp_path / "snapshots")
    (tmp_path / "snapshots").mkdir()
    days = pd.date_range("2011-01-03", "2011-01-23")
    # 1,000 gross a day; in the last week 400 of each day's sales are cancelled
    cancelled = [-400.0 if d >= pd.Timestamp("2011-01-17") else -10.0 for d in days]
    pd.DataFrame({"day": days, "gross_revenue": 1000.0, "cancelled_revenue": cancelled,
                  "net_revenue": [1000.0 + c for c in cancelled], "invoices": 10, "customers": 5}).to_csv(
        tmp_path / "snapshots" / "uci_daily.csv", index=False)
    (tmp_path / "uci_forecast.json").write_text(json.dumps({
        "history": ["2009-12-01", "2011-12-08"], "selected": "combination", "beats_baseline_pct": 19.1,
        "totals": {"next_90_days": {"forecast": 2e6, "backtest_low": 1.8e6, "backtest_high": 2.2e6}}}))
    (tmp_path / "anomalies.json").write_text(json.dumps({"anomalies": [
        {"source": "uci", "metric": "net_revenue", "period": "2011-01-18", "actual": 600.0, "expected": 990.0,
         "z": -4.2, "severity": "moderate"}]}))
    return tmp_path


def test_default_week_is_the_last_complete_monday_to_sunday_week():
    data = pd.DataFrame(index=pd.date_range("2011-01-03", "2011-01-26"))      # ends on a Wednesday
    assert report.week_end(data, None) == pd.Timestamp("2011-01-23")
    assert report.week_end(data, "2011-01-16") == pd.Timestamp("2011-01-16")


def test_week_with_unusual_cancellations_gets_a_recommendation_and_its_anomaly(results):
    s = report.uci_section(pd.Timestamp("2011-01-23"))
    value, wow, _, _ = s["kpis"]["Net revenue"]
    assert value == 7 * 600 and wow == pytest.approx(100 * (4200 / 6930 - 1))
    assert s["kpis"]["Cancellation rate"][0] == pytest.approx(40.0)
    assert any("Cancellations were 40.0% of gross sales, against a typical 1.0%" in r for r in s["recs"])
    assert [a["period"] for a in s["anomalies"]] == ["2011-01-18"]


def test_a_back_dated_report_does_not_show_a_forecast_made_later(results):
    s = report.uci_section(pd.Timestamp("2011-01-23"))
    assert "forecast" not in s
    assert "Plan stock" not in report.render([s])
