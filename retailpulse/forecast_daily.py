"""Daily demand forecast for UCI Online Retail II (real data): net product revenue 30, 60 and 90 days ahead.

Validation is a rolling-origin backtest: at each origin every model sees only the days up to it and is scored on
the next 90. The model with the lowest 90-day WAPE is refit on all days for the forward forecast. MAPE is not used:
closed days (Saturdays, Christmas) are zero revenue.

The Superstore monthly forecast (forecast.py) is a separate analysis and is unchanged."""
import json
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX

from . import config
from .db import query
from .forecast import Z

HORIZONS = (30, 60, 90)
H = max(HORIZONS)
# 11 origins four weeks apart: the earliest test window crosses New Year, as the forward forecast does.
# The 90-day test windows overlap, so fold errors are correlated.
N_ORIGINS, STEP = 11, 28
# Known trading calendar: England & Wales bank holidays and Easter Sundays (gov.uk) outside the Christmas shutdown,
# which the data shows runs Dec 24 - Jan 3 in both years. Every listed day has zero sales in the data.
HOLIDAYS = pd.to_datetime(["2010-04-02", "2010-04-04", "2010-04-05", "2010-05-03", "2010-05-31", "2010-08-30",
                           "2011-04-22", "2011-04-24", "2011-04-25", "2011-04-29", "2011-05-02", "2011-05-30",
                           "2011-08-29"])


def daily_revenue() -> pd.Series:
    """Net revenue for every calendar day, closed days as 0. The last day is dropped: a feed's latest day is
    usually incomplete (here the data stops at 12:50 on 2011-12-09)."""
    d = query("SELECT day, net_revenue FROM uci.daily_sales ORDER BY day")
    s = pd.Series(d["net_revenue"].astype(float).to_numpy(), index=pd.DatetimeIndex(d["day"]), name="revenue")
    return s.iloc[:-1].asfreq("D", fill_value=0.0)


def closed(index: pd.DatetimeIndex) -> np.ndarray:
    """Days the shop is known in advance to be shut (Saturdays are left to the weekly seasonality)."""
    md = index.month * 100 + index.day
    return index.isin(HOLIDAYS) | (md >= 1224) | (md <= 103)


def _future(train: pd.Series, h: int) -> pd.DatetimeIndex:
    return pd.date_range(train.index[-1] + pd.Timedelta(days=1), periods=h, freq="D")


def _naive(train: pd.Series, h: int, lag: int) -> pd.DataFrame:
    """Repeat the value from `lag` days earlier; intervals from the spread of past lag-differences."""
    point = train.iloc[-lag:].to_numpy()[np.arange(h) % lag]
    sd = (train - train.shift(lag)).dropna().std(ddof=1)
    out = pd.DataFrame({"forecast": point}, index=_future(train, h))
    for level, z in Z.items():
        out[f"lo{level}"], out[f"hi{level}"] = point - z * sd, point + z * sd
    return out


def naive_weekly(train: pd.Series, h: int) -> pd.DataFrame:
    return _naive(train, h, 7)


def naive_last_year(train: pd.Series, h: int) -> pd.DataFrame:
    """Same weekday 52 weeks earlier: the simplest model that knows about the autumn peak and Christmas closure."""
    return _naive(train, h, 364)


def holt_winters(train: pd.Series, h: int) -> pd.DataFrame:
    """Additive damped trend, additive weekly seasonality; intervals by simulation."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ExponentialSmoothing(train, trend="add", damped_trend=True, seasonal="add",
                                   seasonal_periods=7).fit(optimized=True)
        sims = fit.simulate(h, repetitions=1000, error="add", random_state=7)
    out = pd.DataFrame({"forecast": fit.forecast(h).to_numpy()}, index=_future(train, h))
    for level in Z:
        a = (100 - level) / 2
        out[f"lo{level}"], out[f"hi{level}"] = np.percentile(sims, a, axis=1), np.percentile(sims, 100 - a, axis=1)
    return out


def _fourier(index: pd.DatetimeIndex, k: int = 2) -> pd.DataFrame:
    t = 2 * np.pi * index.day_of_year.to_numpy() / 365.25
    terms = {f"{f}{i}": fn(i * t) for i in range(1, k + 1) for f, fn in (("sin", np.sin), ("cos", np.cos))}
    return pd.DataFrame({**terms, "closed": closed(index).astype(float)}, index=index)


def sarimax_fourier(train: pd.Series, h: int) -> pd.DataFrame:
    """SARIMA(1,0,1)(0,1,1)7 for the weekly pattern; regressors: two annual Fourier pairs for the autumn peak and
    a closed-day dummy."""
    future = _future(train, h)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = SARIMAX(train, exog=_fourier(train.index), order=(1, 0, 1),
                      seasonal_order=(0, 1, 1, 7)).fit(disp=False)
        fc = fit.get_forecast(h, exog=_fourier(future))
    out = pd.DataFrame({"forecast": fc.predicted_mean.to_numpy()}, index=future)
    for level in Z:
        ci = fc.conf_int(alpha=1 - level / 100).to_numpy()
        out[f"lo{level}"], out[f"hi{level}"] = ci[:, 0], ci[:, 1]
    return out


def combination(train: pd.Series, h: int) -> pd.DataFrame:
    """Equal-weight average of SARIMAX and last year: SARIMAX tracks recent level, last year knows the post-Christmas
    drop that SARIMAX overshoots. Bounds are averaged too, an approximation rather than a derived interval."""
    return (sarimax_fourier(train, h) + naive_last_year(train, h)) / 2


BASELINE = "naive_weekly"
METHODS = {"naive_weekly": naive_weekly, "naive_last_year": naive_last_year,
           "holt_winters": holt_winters, "sarimax_fourier": sarimax_fourier,
           "combination": combination}


def origins(s: pd.Series) -> list[pd.Timestamp]:
    """Last training day of each backtest fold, newest leaves exactly H days to score."""
    last = s.index[-1] - pd.Timedelta(days=H)
    return [last - pd.Timedelta(days=STEP * i) for i in reversed(range(N_ORIGINS))]


def predict(train: pd.Series, method: str, h: int = H) -> pd.DataFrame:
    """Any model's forecast, set to 0 on days the calendar says the shop is shut."""
    fc = METHODS[method](train, h)
    fc.loc[closed(fc.index)] = 0.0
    return fc


def forecast_at(s: pd.Series, origin: pd.Timestamp, method: str) -> pd.DataFrame:
    """Fit on days up to and including `origin` only."""
    return predict(s.loc[:origin], method)


def score(actual: pd.Series, fc: pd.DataFrame, h: int) -> dict:
    a, f = actual.iloc[:h], fc.iloc[:h]
    err = a.to_numpy() - f["forecast"].to_numpy()
    return {"wape_pct": 100 * np.abs(err).sum() / np.abs(a).sum(), "mae": np.abs(err).mean(),
            "total_error_pct": 100 * (f["forecast"].sum() / a.sum() - 1),
            "coverage80_pct": 100 * ((a >= f["lo80"]) & (a <= f["hi80"])).mean(),
            "coverage95_pct": 100 * ((a >= f["lo95"]) & (a <= f["hi95"])).mean()}


def backtest(s: pd.Series, methods=METHODS) -> pd.DataFrame:
    rows = []
    for o in origins(s):
        actual = s.loc[o + pd.Timedelta(days=1):].iloc[:H]
        for m in methods:
            fc = forecast_at(s, o, m)
            rows += [{"model": m, "origin": o.date(), "horizon": h, **score(actual, fc, h)} for h in HORIZONS]
    return pd.DataFrame(rows)


def run() -> dict:
    s = daily_revenue()
    bt = backtest(s)
    summary = bt.groupby(["model", "horizon"])[["wape_pct", "mae", "total_error_pct", "coverage80_pct",
                                                "coverage95_pct"]].mean().round(2)
    best = summary.xs(H, level="horizon")["wape_pct"].idxmin()
    future = predict(s, best)
    # range of the chosen model's own backtest errors on each horizon total, applied to the new totals
    errs = bt[bt["model"] == best].groupby("horizon")["total_error_pct"]
    totals = {}
    for h in HORIZONS:
        point = float(future["forecast"].iloc[:h].sum())
        lo, hi = errs.get_group(h).min(), errs.get_group(h).max()
        # forecast = actual * (1 + e/100)  ->  actual = forecast / (1 + e/100)
        totals[f"next_{h}_days"] = {"forecast": round(point, 2), "backtest_low": round(point / (1 + hi / 100), 2),
                                    "backtest_high": round(point / (1 + lo / 100), 2)}
    out = {
        "source": "UCI Online Retail II (real), net product revenue in GBP",
        "history": [str(s.index[0].date()), str(s.index[-1].date())],
        "forecast_start": str(future.index[0].date()),
        "backtest": {"origins": [str(o.date()) for o in origins(s)], "horizon_days": H,
                     "note": "origins 28 days apart, so 90-day test windows overlap and errors are correlated"},
        "scores": {m: {str(h): summary.loc[(m, h)].to_dict() for h in HORIZONS} for m in METHODS},
        "year_end_fold": {m: bt[(bt["origin"] == bt["origin"].min()) & (bt["model"] == m) & (bt["horizon"] == H)]
                          [["wape_pct", "total_error_pct"]].iloc[0].round(2).to_dict() for m in METHODS},
        "selected": best, "selection_rule": "lowest mean 90-day WAPE in the backtest",
        "baseline": BASELINE,
        "beats_baseline_pct": round(float(summary.loc[(BASELINE, H), "wape_pct"] - summary.loc[(best, H), "wape_pct"]), 2),
        "totals": totals,
    }
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "uci_forecast.json").write_text(json.dumps(out, indent=2, default=float))
    daily = pd.concat([s.iloc[-180:].to_frame("actual"), future]).rename_axis("day").round(2)
    daily.to_csv(config.RESULTS_DIR / "uci_forecast.csv")
    return out


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=float))
