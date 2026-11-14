"""Discount optimization and what-if discount caps.

Thresholds and exposure are observed (synthetic Superstore data). The cap scenarios are *modeled*: they reprice
historical lines and assume a share of capped volume walks away. They estimate an opportunity, not a saving.

Model for a line with list price `gross_sales`, discount `d` and cost `implied_cost` (= sales - profit):
    capped price   sales' = gross_sales * (1 - min(d, cap))
    demand loss    lines with d > cap keep (1 - loss) of their volume, so sales' and cost both scale by (1 - loss)
    cost per unit is unchanged; uncapped lines are untouched.
"""
import json

import pandas as pd

from . import analysis, config

CAPS = [0.10, 0.15, 0.20, 0.25]
DEMAND_LOSS = [0.0, 0.10, 0.25, 0.50, 1.0]   # 1.0 = capped lines are not sold at all
PLANNING_LOSS = 0.25    # demand-loss assumption the recommendation is reported at
MIN_LINES = 20          # a discount level needs this many lines in a sub-category before its margin is reported


def threshold_table(df: pd.DataFrame, by: str) -> pd.DataFrame:
    """Per group: margin at each observed discount level, and the lowest level where margin turns negative."""
    lvl = (df.groupby([by, "discount"]).agg(lines=("sales", "size"), sales=("sales", "sum"), profit=("profit", "sum"))
           .reset_index().query("lines >= @MIN_LINES"))
    lvl["margin"] = lvl["profit"] / lvl["sales"]
    rows = []
    for g, part in lvl.groupby(by):
        neg = part[part["margin"] < 0]
        ok = part[part["margin"] >= 0]
        rows.append({by: g,
                     "max_profitable_discount": float(ok["discount"].max()) if len(ok) else None,
                     "loss_threshold_discount": float(neg["discount"].min()) if len(neg) else None,
                     "profit_on_loss_lines": round(float(df[(df[by] == g) & (df["profit"] < 0)]["profit"].sum()), 2)})
    cols = [by, "max_profitable_discount", "loss_threshold_discount", "profit_on_loss_lines"]
    return pd.DataFrame(rows, columns=cols).sort_values("profit_on_loss_lines")


def vulnerable_products(df: pd.DataFrame, above: float = 0.20, top: int = 10) -> pd.DataFrame:
    """Products losing the most profit on lines discounted above `above`."""
    deep = df[df["discount"] > above]
    out = (deep.groupby(["product_name", "sub_category"])
           .agg(deep_lines=("sales", "size"), deep_sales=("sales", "sum"), deep_profit=("profit", "sum"))
           .reset_index().sort_values("deep_profit").head(top))
    return out.round(2)


def cap(df: pd.DataFrame, limit: float, loss: float = 0.0, sub_categories=None) -> dict:
    """Revenue, profit and margin if no discount exceeded `limit` and `loss` of the capped volume was lost."""
    hit = df["discount"] > limit
    if sub_categories is not None:
        hit &= df["sub_category"].isin(sub_categories)
    keep = 1 - loss
    sales = df["sales"].where(~hit, df["gross_sales"] * (1 - limit) * keep)
    cost = df["implied_cost"].where(~hit, df["implied_cost"] * keep)
    base_sales, base_profit = df["sales"].sum(), df["profit"].sum()
    new_sales, new_profit = sales.sum(), (sales - cost).sum()
    by_level = df[hit].groupby("discount")["profit"].sum()
    return {"cap": limit, "demand_loss": loss, "lines_capped": int(hit.sum()),
            "capped_lines_baseline_profit": round(float(by_level.sum()), 2),
            # True when every discount level the cap touches loses money today: then profit cannot fall,
            # whatever share of that volume is lost. A tighter cap that reaches profitable levels fails this.
            "only_loss_making_levels": bool((by_level < 0).all()),
            "revenue": round(float(new_sales), 2), "profit": round(float(new_profit), 2),
            "margin_pct": round(100 * float(new_profit / new_sales), 2),
            "revenue_change": round(float(new_sales - base_sales), 2),
            "profit_change": round(float(new_profit - base_profit), 2),
            "margin_change_pp": round(100 * float(new_profit / new_sales - base_profit / base_sales), 2)}


def _records(t: pd.DataFrame) -> list[dict]:
    return t.astype(object).where(t.notna(), None).to_dict("records")     # NaN is not valid JSON


def grid(df: pd.DataFrame, sub_categories=None) -> pd.DataFrame:
    return pd.DataFrame([cap(df, c, l, sub_categories) for c in CAPS for l in DEMAND_LOSS])


def recommend(scenarios: pd.DataFrame) -> dict:
    """No-regret rule: among caps that touch only loss-making discount levels (so profit cannot fall whatever share
    of that volume is lost), the one with the largest profit gain at the planning demand loss. Tighter caps gain more
    on paper but cut into profitable lines and rest entirely on the demand assumption."""
    at = scenarios[scenarios["demand_loss"] == PLANNING_LOSS]
    safe = at[at["only_loss_making_levels"]]
    pool = safe if len(safe) else at
    best = pool.loc[pool["profit_change"].idxmax()]
    return {"rule": "largest profit_change at 25% demand loss among caps touching only loss-making discount levels",
            "no_regret": bool(len(safe)), **{k: (int(v) if k == "lines_capped" else v) for k, v in best.items()}}


def _charts(df: pd.DataFrame, scenarios: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = config.ROOT / "docs" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    lvl = df.groupby("discount").agg(sales=("sales", "sum"), profit=("profit", "sum"))
    m = 100 * lvl["profit"] / lvl["sales"]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar([f"{d:.0%}" for d in m.index], m, color=["#2a78d6" if v >= 0 else "#eb6834" for v in m], width=0.6)
    ax.axhline(0, color="#555", lw=1)
    ax.set(title="Profit margin by discount level (all years, synthetic data)", xlabel="Discount", ylabel="Margin %")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(out / "margin_by_discount.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4))
    for c, color in zip(CAPS, ["#2a78d6", "#1baa7a", "#9b59d0", "#eb6834"]):
        s = scenarios[scenarios["cap"] == c]
        ax.plot(100 * s["demand_loss"], s["profit_change"] / 1000, marker="o", lw=2, color=color, label=f"cap {c:.0%}")
    ax.axhline(0, color="#555", lw=1)
    ax.set(title="Modeled profit change vs baseline, latest year", xlabel="Demand lost on capped lines (%)",
           ylabel="Profit change ($K)")
    ax.legend(frameon=False); ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(out / "cap_scenarios.png", dpi=150); plt.close(fig)


def run(charts: bool = True) -> dict:
    df = analysis.load_lines()
    latest = df[df["year"] == df["year"].max()]
    scenarios = grid(latest)
    by_sub = threshold_table(df, "sub_category")
    losing = by_sub.loc[by_sub["loss_threshold_discount"].le(0.20), "sub_category"].tolist()
    targeted = grid(latest, losing)
    out = {
        "note": "Thresholds are observed associations; cap scenarios are modeled estimates, not realized savings. "
                "Data is synthetic (Tableau Sample Superstore).",
        "year": int(latest["year"].iloc[0]),
        "baseline": {"revenue": round(float(latest["sales"].sum()), 2), "profit": round(float(latest["profit"].sum()), 2),
                     "margin_pct": round(100 * analysis.margin(latest), 2)},
        "thresholds_by_category": _records(threshold_table(df, "category")),
        "thresholds_by_sub_category": _records(by_sub),
        "vulnerable_products": vulnerable_products(df).to_dict("records"),
        "blanket_caps": scenarios.to_dict("records"),
        "targeted_caps": {"sub_categories": losing, "scenarios": targeted.to_dict("records")},
        "recommended": {"blanket": recommend(scenarios), "targeted": recommend(targeted)},
    }
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "scenarios.json").write_text(json.dumps(out, indent=2, default=float))
    pd.concat([scenarios.assign(scope="all"), targeted.assign(scope="targeted")]).to_csv(
        config.RESULTS_DIR / "scenarios.csv", index=False)
    if charts:
        _charts(df, scenarios)
    return out


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=float))
