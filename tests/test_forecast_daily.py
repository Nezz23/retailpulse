import numpy as np
import pandas as pd
import pytest

from retailpulse import forecast_daily as fd, ingest
from tests.test_ingest import lines

DAYS = pd.date_range("2009-12-01", "2011-06-30", freq="D")
# weekday pattern plus noise, zero on known closures and Saturdays, like the real series
SERIES = pd.Series(np.where(fd.closed(DAYS) | (DAYS.day_of_week == 5), 0.0,
                            1000 + 200 * DAYS.day_of_week.to_numpy() + np.random.default_rng(0).normal(0, 50, len(DAYS))),
                   index=DAYS)


def test_a_forecast_never_sees_days_after_its_origin():
    origin = pd.Timestamp("2011-03-01")
    future_changed = SERIES.copy()
    future_changed.loc[origin + pd.Timedelta(days=1):] *= 1000
    a = fd.forecast_at(SERIES, origin, "combination")
    b = fd.forecast_at(future_changed, origin, "combination")
    pd.testing.assert_frame_equal(a, b)


def test_forecast_is_zero_on_known_closures_only():
    fc = fd.predict(SERIES.loc[:"2010-12-15"], "sarimax_fourier", 30)
    assert fc.loc["2010-12-25", "forecast"] == 0 and fc.loc["2011-01-03", "hi95"] == 0
    assert fc.loc["2010-12-21", "forecast"] > 0 and fc.loc["2011-01-04", "forecast"] > 0


def test_weekly_naive_repeats_last_week():
    week = pd.Series([1.0, 2, 3, 4, 5, 6, 7], index=pd.date_range("2011-02-07", periods=7))
    assert list(fd.naive_weekly(pd.concat([week.shift(-7, freq="D"), week]), 10)["forecast"]) == \
        [1, 2, 3, 4, 5, 6, 7, 1, 2, 3]


def test_horizon_scores():
    actual = pd.Series([100.0, 0.0, 300.0])
    fc = pd.DataFrame({"forecast": [110.0, 0.0, 270.0], "lo80": 90.0, "hi80": 280.0, "lo95": 0.0, "hi95": 400.0})
    r = fd.score(actual, fc, 3)
    assert r["wape_pct"] == pytest.approx(100 * 40 / 400)        # |err| 10 + 0 + 30 over actual 400
    assert r["total_error_pct"] == pytest.approx(100 * (380 / 400 - 1))
    assert r["coverage80_pct"] == pytest.approx(100 / 3)          # only the first day is inside 90-280
    assert r["coverage95_pct"] == pytest.approx(100.0)


def test_daily_series_counts_closed_days_as_zero_and_drops_the_partial_last_day(uci_db):
    ingest.load_window(lines([("1", "85048", 1, "2010-01-04 10:00", 5.0, "1"),
                              ("2", "85048", 1, "2010-01-06 10:00", 7.0, "1"),
                              ("3", "85048", 1, "2010-01-07 09:00", 9.0, "1")]), pd.Timestamp("2010-01-08"))
    s = fd.daily_revenue()
    assert list(s.index.strftime("%m-%d")) == ["01-04", "01-05", "01-06"]
    assert list(s) == [5.0, 0.0, 7.0]
