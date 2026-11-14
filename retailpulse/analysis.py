"""Statistics behind the dashboards: is the margin decline real, and how strongly is discounting associated
with margin once product mix is held fixed? Everything here is association, not causation."""
import json

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from . import config
from .db import query

RNG_SEED = 7


def load_lines() -> pd.DataFrame:
    df = query("SELECT * FROM analytics.sales_wide")
    for c in ("discount", "gross_sales", "discount_amount", "sales", "profit", "implied_cost"):
        df[c] = df[c].astype(float)
    df["year"] = pd.to_datetime(df["order_date"]).dt.year
    df["line_margin"] = df["profit"] / df["sales"]
    return df


def margin(df: pd.DataFrame) -> float:
    return df["profit"].sum() / df["sales"].sum()


def margin_change_ci(df: pd.DataFrame, year: int, n_boot: int = 2000) -> dict:
    """Bootstrap CI for margin(year) - margin(year - 1), resampling whole orders within each year."""
    rng = np.random.default_rng(RNG_SEED)
    by_order = df.groupby(["year", "order_id"])[["sales", "profit"]].sum().reset_index()
    cur = by_order[by_order["year"] == year][["sales", "profit"]].to_numpy()
    prev = by_order[by_order["year"] == year - 1][["sales", "profit"]].to_numpy()

    def m(a: np.ndarray) -> float:
        return a[:, 1].sum() / a[:, 0].sum()

    diffs = np.array([m(cur[rng.integers(0, len(cur), len(cur))]) - m(prev[rng.integers(0, len(prev), len(prev))])
                      for _ in range(n_boot)])
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"year": year, "margin_prev_pct": round(100 * m(prev), 2), "margin_pct": round(100 * m(cur), 2),
            "change_pp": round(100 * (m(cur) - m(prev)), 2), "ci95_pp": [round(100 * lo, 2), round(100 * hi, 2)],
            "share_of_bootstrap_below_zero": round(float((diffs < 0).mean()), 3), "orders_resampled": n_boot}


def discount_association(df: pd.DataFrame) -> dict:
    """Line margin on discount, with and without sub-category fixed effects (HC1 robust SEs)."""
    rho, p_rho = stats.spearmanr(df["discount"], df["line_margin"])
    raw = smf.ols("line_margin ~ discount", df).fit(cov_type="HC1")
    fe = smf.ols("line_margin ~ discount + C(sub_category) + C(region) + C(segment)", df).fit(cov_type="HC1")
    by_level = (df.groupby("discount").apply(lambda g: pd.Series({"lines": len(g), "margin_pct": 100 * margin(g)}),
                                             include_groups=False).round(2).reset_index())
    first_negative = float(by_level.loc[by_level["margin_pct"] < 0, "discount"].min())
    lo, hi = fe.conf_int().loc["discount"]
    return {
        "lines": len(df),
        "spearman_rho": round(float(rho), 3), "spearman_p": float(p_rho),
        "slope_pp_per_10pt_discount_raw": round(10 * float(raw.params["discount"]), 2),
        "slope_pp_per_10pt_discount_controlled": round(10 * float(fe.params["discount"]), 2),
        "slope_ci95_controlled": [round(10 * float(lo), 2), round(10 * float(hi), 2)],
        "r2_controlled": round(float(fe.rsquared), 3),
        "controls": ["sub_category", "region", "segment"],
        "lowest_discount_level_with_negative_margin": first_negative,
        "margin_by_discount_level": by_level.to_dict("records"),
    }


def margin_drivers(df: pd.DataFrame, year: int) -> dict:
    """Sub-categories whose margin fell most year over year, with the change in their discount rate."""
    g = df[df["year"].isin([year - 1, year])].groupby(["sub_category", "year"]).agg(
        sales=("sales", "sum"), profit=("profit", "sum"), gross=("gross_sales", "sum"),
        disc=("discount_amount", "sum"))
    g["margin"] = g["profit"] / g["sales"]
    g["discount_rate"] = g["disc"] / g["gross"]
    w = g[["margin", "discount_rate", "sales"]].unstack("year")
    out = pd.DataFrame({
        "margin_prev_pct": 100 * w[("margin", year - 1)], "margin_pct": 100 * w[("margin", year)],
        "discount_rate_prev_pct": 100 * w[("discount_rate", year - 1)],
        "discount_rate_pct": 100 * w[("discount_rate", year)],
        "revenue": w[("sales", year)]})
    out["margin_change_pp"] = out["margin_pct"] - out["margin_prev_pct"]
    out["discount_rate_change_pp"] = out["discount_rate_pct"] - out["discount_rate_prev_pct"]
    rho, p = stats.spearmanr(out["discount_rate_change_pp"], out["margin_change_pp"])
    rows = out.sort_values("margin_change_pp").round(2).reset_index().to_dict("records")
    return {"year": year, "sub_categories": rows,
            "spearman_discount_change_vs_margin_change": round(float(rho), 3), "p_value": round(float(p), 4)}


def concentration(df: pd.DataFrame) -> dict:
    prod = df.groupby(["product_id", "product_name"])["profit"].sum().round(2)  # cents: float sums of break-even products land at -1e-15
    losers = prod[prod < 0]
    state = df.groupby("state")[["sales", "profit"]].sum().round(2)
    loss_states = state[state["profit"] < 0].sort_values("profit")
    return {
        "unprofitable_products": len(losers), "products": len(prod),
        "unprofitable_products_loss": round(float(losers.sum()), 2),
        "loss_as_pct_of_total_profit": round(100 * float(-losers.sum() / df["profit"].sum()), 2),
        "loss_making_states": loss_states.index.tolist(),
        "loss_making_states_loss": round(float(loss_states["profit"].sum()), 2),
        "loss_making_states_revenue_share_pct": round(100 * float(loss_states["sales"].sum() / df["sales"].sum()), 2),
    }


def run() -> dict:
    df = load_lines()
    last = int(df["year"].max())
    out = {
        "margin_change": [margin_change_ci(df, y) for y in sorted(df["year"].unique())[1:]],
        "discount_association": discount_association(df),
        "margin_drivers": margin_drivers(df, last),
        "concentration": concentration(df),
    }
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "analysis.json").write_text(json.dumps(out, indent=2, default=float))
    return out


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=float))
