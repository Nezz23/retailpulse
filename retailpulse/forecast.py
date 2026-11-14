"""Monthly revenue forecast with time-based validation.

Hold out the last 12 months, fit on everything before, compare three methods on the holdout (MAE, MAPE,
interval coverage), then refit the winner on all months and forecast the next 12 with 80% / 95% intervals."""
import json
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX

from . import config
from .db import query

HORIZON = 12
Z = {80: 1.2816, 95: 1.9600}


def monthly_revenue() -> pd.Series:
    m = query("SELECT month, revenue FROM analytics.monthly_trends ORDER BY month")
    s = pd.Series(m["revenue"].astype(float).to_numpy(), index=pd.DatetimeIndex(m["month"]), name="revenue")
    return s.asfreq("MS")


def seasonal_naive(train: pd.Series, h: int) -> pd.DataFrame:
    """Same month last year; intervals from the spread of past year-over-year errors."""
    point = train.iloc[-12:].to_numpy()[np.arange(h) % 12]
    sd = (train - train.shift(12)).dropna().std(ddof=1)
    return _frame(train, h, point, np.full(h, sd))


def ets(train: pd.Series, h: int) -> pd.DataFrame:
    """Holt-Winters, additive damped trend, multiplicative seasonality; intervals by simulation."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ExponentialSmoothing(train, trend="add", damped_trend=True, seasonal="mul",
                                   seasonal_periods=12).fit(optimized=True)
        sims = fit.simulate(h, repetitions=2000, error="mul", random_state=7)
    out = pd.DataFrame({"forecast": fit.forecast(h).to_numpy()}, index=_future(train, h))
    for level in (80, 95):
        a = (100 - level) / 2
        out[f"lo{level}"] = np.percentile(sims, a, axis=1)
        out[f"hi{level}"] = np.percentile(sims, 100 - a, axis=1)
    return out


def sarima(train: pd.Series, h: int) -> pd.DataFrame:
    """SARIMA(0,1,1)(0,1,1)12 on log revenue (the 'airline' model); intervals back-transformed."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = SARIMAX(np.log(train), order=(0, 1, 1), seasonal_order=(0, 1, 1, 12)).fit(disp=False)
        fc = fit.get_forecast(h)
    out = pd.DataFrame({"forecast": np.exp(fc.predicted_mean.to_numpy())}, index=_future(train, h))
    for level in (80, 95):
        ci = np.exp(fc.conf_int(alpha=1 - level / 100).to_numpy())
        out[f"lo{level}"], out[f"hi{level}"] = ci[:, 0], ci[:, 1]
    return out


METHODS = {"seasonal_naive": seasonal_naive, "holt_winters": ets, "sarima": sarima}


def _future(train: pd.Series, h: int) -> pd.DatetimeIndex:
    return pd.date_range(train.index[-1] + pd.offsets.MonthBegin(1), periods=h, freq="MS")


def _frame(train: pd.Series, h: int, point: np.ndarray, sd: np.ndarray) -> pd.DataFrame:
    out = pd.DataFrame({"forecast": point}, index=_future(train, h))
    for level, z in Z.items():
        out[f"lo{level}"], out[f"hi{level}"] = point - z * sd, point + z * sd
    return out


def score(actual: pd.Series, fc: pd.DataFrame) -> dict:
    err = actual.to_numpy() - fc["forecast"].to_numpy()
    return {
        "mae": round(float(np.abs(err).mean()), 2),
        "mape_pct": round(float(100 * np.abs(err / actual.to_numpy()).mean()), 2),
        "annual_total_error_pct": round(float(100 * (fc["forecast"].sum() / actual.sum() - 1)), 2),
        "coverage80_pct": round(float(100 * ((actual >= fc["lo80"]) & (actual <= fc["hi80"])).mean()), 1),
        "coverage95_pct": round(float(100 * ((actual >= fc["lo95"]) & (actual <= fc["hi95"])).mean()), 1),
    }


def seasonality(s: pd.Series) -> pd.DataFrame:
    """Each calendar month's revenue relative to its year's monthly average (1.0 = an average month)."""
    df = pd.DataFrame({"revenue": s.to_numpy(), "year": s.index.year, "month": s.index.month})
    df["index"] = df["revenue"] / df.groupby("year")["revenue"].transform("mean")
    return df.groupby("month")["index"].agg(["mean", "min", "max"]).round(3).reset_index()


def run() -> dict:
    s = monthly_revenue()
    train, test = s.iloc[:-HORIZON], s.iloc[-HORIZON:]
    holdout, scores = {}, {}
    for name, fn in METHODS.items():
        holdout[name] = fn(train, HORIZON)
        scores[name] = score(test, holdout[name])
    best = min(scores, key=lambda k: scores[k]["mape_pct"])
    future = METHODS[best](s, HORIZON)

    rows = [pd.DataFrame({"month": s.index, "series": "actual", "revenue": s.to_numpy()})]
    for name, fc in holdout.items():
        rows.append(fc.reset_index(names="month").assign(series=f"holdout_{name}",
                                                         actual=test.to_numpy()))
    rows.append(future.reset_index(names="month").assign(series=f"forecast_{best}"))
    long = pd.concat(rows, ignore_index=True)
    config.TABLEAU_DIR.mkdir(parents=True, exist_ok=True)
    long.round({"revenue": 2, "forecast": 2, "actual": 2, "lo80": 2, "hi80": 2, "lo95": 2, "hi95": 2}).to_csv(config.TABLEAU_DIR / "forecast.csv", index=False)
    seasonality(s).to_csv(config.TABLEAU_DIR / "seasonality.csv", index=False)

    out = {"train": [str(train.index[0].date()), str(train.index[-1].date())],
           "test": [str(test.index[0].date()), str(test.index[-1].date())],
           "holdout_scores": scores, "selected": best, "selection_rule": "lowest holdout MAPE",
           "next_12_months_total": round(float(future["forecast"].sum()), 2)}
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "forecast.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
