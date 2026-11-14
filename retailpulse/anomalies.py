"""Unusual revenue, profit and margin movements, with severity and context. Context is what moved alongside the
anomaly (which sub-categories, how concentrated the day was); it is description, not a root cause.

- Superstore (synthetic), monthly revenue / profit / margin: expected = this year's level + the calendar-month pattern of the
  other three years (leave-one-year-out medians; log scale for revenue), residual scored as a robust z-score (median and MAD). Retrospective: it uses
  all four years. Four seasonal cycles are too few for STL or an in-sample fit, which
  fit nearly every point, shrink the residual spread and flag noise.
- UCI Online Retail II (real), daily net revenue on trading days: log ratio to the median of the same weekday over
  the previous 8 weeks, scaled by the spread of that ratio over the previous 60 trading days. Trailing only, so it
  could run each morning on yesterday's data.
"""
import json

import numpy as np
import pandas as pd

from . import analysis, config, forecast_daily
from .db import query

# |robust z| at or above; below 4 is not flagged. Calibrated by simulation (tests/test_anomalies.py): on noise-only
# 4-year monthly data about 0.7% of months reach 4 (2.6% would reach 3), i.e. roughly one false flag per 144 cells.
SEVERITY = [(6.0, "severe"), (5.0, "high"), (4.0, "moderate")]
WEEKS = 8


def robust_z(x: pd.Series) -> pd.Series:
    mad = (x - x.median()).abs().median()
    return (x - x.median()) / (1.4826 * mad)


def severity(z: float) -> str | None:
    return next((label for cut, label in SEVERITY if abs(z) >= cut), None)


def monthly(df: pd.DataFrame) -> pd.DataFrame:
    m = df.groupby(pd.to_datetime(df["order_date"]).dt.to_period("M").dt.to_timestamp())[["sales", "profit"]].sum()
    return m.assign(margin=m["profit"] / m["sales"]).rename(columns={"sales": "revenue"}).asfreq("MS")


def two_way_expected(x: pd.Series) -> pd.Series:
    """Expected value for each month from the *other* years: their median calendar-month pattern, shifted to this
    year's own median level. Out-of-sample, so a month cannot hide itself and the residual spread is honest; with
    three other years the medians also keep one extreme month from leaking into the others."""
    table = pd.DataFrame({"v": x.to_numpy(), "y": x.index.year, "m": x.index.month}).pivot(index="y", columns="m",
                                                                                         values="v")
    fitted = table * np.nan
    for y in table.index:
        others = table.drop(y)
        pattern = others.sub(others.median(axis=1), axis=0).median(axis=0)
        fitted.loc[y] = (table.loc[y] - pattern).median() + pattern
    return pd.Series([fitted.at[t.year, t.month] for t in x.index], index=x.index)


def superstore(df: pd.DataFrame) -> list[dict]:
    m = monthly(df)
    month = pd.to_datetime(df["order_date"]).dt.to_period("M").dt.to_timestamp()
    out = []
    for metric in ("revenue", "profit", "margin"):
        x = np.log(m[metric]) if metric == "revenue" else m[metric]
        fitted = two_way_expected(x)
        z = robust_z(x - fitted)
        expected = np.exp(fitted) if metric == "revenue" else fitted
        for t in z.index[z.abs() >= SEVERITY[-1][0]]:
            out.append({"source": "superstore", "metric": metric, "period": str(t.date()),
                        "actual": round(float(m.loc[t, metric]), 4), "expected": round(float(expected[t]), 4),
                        "z": round(float(z[t]), 2), "severity": severity(z[t]), "context": _subcategory_moves(df, month, t)})
    return out


def _subcategory_moves(df: pd.DataFrame, month: pd.Series, t: pd.Timestamp) -> dict:
    """The three sub-categories whose revenue and profit changed most against the same month a year earlier."""
    prev = t - pd.DateOffset(years=1)
    cur = df[month == t].groupby("sub_category")[["sales", "profit"]].sum()
    if not (month == prev).any():
        return {"note": "no same month a year earlier to compare with"}
    delta = cur.sub(df[month == prev].groupby("sub_category")[["sales", "profit"]].sum(), fill_value=0)
    return {"vs": str(prev.date()), **{f"largest_{c}_changes": {k: round(float(v), 2) for k, v in
                                       delta[c].reindex(delta[c].abs().sort_values(ascending=False).index).head(3).items()}
                                       for c in ("sales", "profit")}}


def uci() -> list[dict]:
    s = forecast_daily.daily_revenue()
    trading = s[~forecast_daily.closed(s.index) & (s.index.day_of_week != 5)].clip(lower=1.0)
    # median of the previous 8 same weekdays, never including the day itself
    expected = trading.groupby(trading.index.day_of_week, group_keys=False).apply(
        lambda d: d.shift(1).rolling(WEEKS).median())
    r = np.log(trading / expected)
    prior = r.shift(1).rolling(60, min_periods=30)
    z = (r - prior.median()) / (1.4826 * prior.apply(lambda w: np.median(np.abs(w - np.median(w))), raw=True))
    out = [{"source": "uci", "metric": "net_revenue", "period": str(t.date()), "actual": round(float(trading[t]), 2),
            "expected": round(float(expected[t]), 2), "z": round(float(z[t]), 2), "severity": severity(z[t]),
            "context": _day_context(str(t.date()))} for t in z.index[z.abs() >= SEVERITY[-1][0]]]
    return out


def _day_context(day: str) -> dict:
    inv = query("""SELECT invoice, sum(quantity * price) AS value, min(country) AS country FROM uci.lines
                   WHERE invoice_ts::date = %s AND stock_code ~ '^[0-9]{5}' AND price > 0 AND invoice NOT LIKE 'A%%'
                   GROUP BY invoice""", (day,))
    sales = inv[~inv["invoice"].str.startswith("C")]
    top = sales.loc[sales["value"].idxmax()] if len(sales) else None
    near = pd.date_range(pd.Timestamp(day) - pd.Timedelta(days=3), periods=7)
    return {"within_3_days_of_known_closure": bool(forecast_daily.closed(near).any()),
            "invoices": int(len(sales)),
            "cancelled_value": round(float(inv.loc[inv["invoice"].str.startswith("C"), "value"].sum()), 2),
            "largest_invoice_share_pct": round(100 * float(top["value"] / sales["value"].sum()), 1) if top is not None else None,
            "largest_invoice_country": top["country"] if top is not None else None}


def run() -> dict:
    found = superstore(analysis.load_lines()) + uci()
    out = {"method": {"superstore": "robust STL residual, monthly, robust z", "uci": f"same weekday, trailing {WEEKS} weeks, robust z",
                      "severity": {label: f"|z| >= {cut}" for cut, label in SEVERITY}},
           "note": "Context lists what moved with each anomaly. It is not a diagnosed cause.",
           "counts": pd.DataFrame(found).groupby(["source", "severity"]).size().to_dict() if found else {},
           "anomalies": found}
    out["counts"] = {f"{k[0]}:{k[1]}": int(v) for k, v in out["counts"].items()}
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "anomalies.json").write_text(json.dumps(out, indent=2, default=float))
    return out


if __name__ == "__main__":
    r = run()
    print(json.dumps(r["counts"], indent=2))
