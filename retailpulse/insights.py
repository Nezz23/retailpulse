"""Dashboard 6 content: each finding is built from the results files, with its evidence and its limits."""
import calendar
import json

import pandas as pd

from . import config
from .db import query


def _load(name: str) -> dict:
    return json.loads((config.RESULTS_DIR / name).read_text())


def build() -> list[dict]:
    a, f = _load("analysis.json"), _load("forecast.json")
    k = query("SELECT * FROM analytics.yearly_kpis ORDER BY year").iloc[-1]
    mc = a["margin_change"][-1]
    da, md, c = a["discount_association"], a["margin_drivers"], a["concentration"]
    top3 = md["sub_categories"][:3]
    bands = query("SELECT * FROM analytics.discount_bands").set_index("discount_band")
    hw, sa = f["holdout_scores"]["holt_winters"], f["holdout_scores"]["sarima"]
    season = pd.read_csv(config.TABLEAU_DIR / "seasonality.csv")
    peaks = season[season["mean"] > 1.5]
    peak_text = (", ".join((calendar.month_abbr[m] for m in peaks["month"])) +
                 f" run {100 * (peaks['mean'].min() - 1):.0f}-{100 * (peaks['mean'].max() - 1):.0f}% above an average month")
    central = query("SELECT region, sum(profit) / sum(revenue) * 100 AS m FROM analytics.regional_performance "
                    "GROUP BY 1 ORDER BY 2").iloc[0]
    return [
        {"area": "What happened", "type": "Descriptive",
         "finding": f"{int(k.year)} revenue grew {k.revenue_yoy_pct}% but profit grew {k.profit_yoy_pct}%; "
                    f"margin moved {mc['change_pp']:+}pp to {mc['margin_pct']}%.",
         "uncertainty": f"Bootstrap 95% CI for the margin change is {mc['ci95_pp'][0]} to {mc['ci95_pp'][1]}pp: "
                        "the overall dip is not distinguishable from normal year-to-year noise.",
         "action": "Treat the dip as an early signal and look at where it is concentrated, not as a proven decline."},
        {"area": "Why it might have happened", "type": "Association",
         "finding": "Margins fell most in " + ", ".join(
             f"{r['sub_category']} ({r['margin_change_pp']:+}pp, discount rate {r['discount_rate_change_pp']:+}pp)"
             for r in top3) + ".",
         "uncertainty": f"Across all 17 sub-categories, a deeper discount change goes with a larger margin drop "
                        f"(Spearman rho {md['spearman_discount_change_vs_margin_change']}, p {md['p_value']}). "
                        "Correlation, not proof of cause.",
         "action": "Review the discount policy for these three sub-categories first."},
        {"area": "Why it matters", "type": "Descriptive",
         "finding": f"Lines discounted above 20% are {bands.loc['21-40%', 'revenue_share_pct'] + bands.loc['41-80%', 'revenue_share_pct']:.1f}% "
                    f"of revenue but lose ${-(bands.loc['21-40%', 'profit'] + bands.loc['41-80%', 'profit']):,.0f}; "
                    f"every discount level from {int(100 * da['lowest_discount_level_with_negative_margin'])}% up has a negative margin.",
         "uncertainty": f"Holding sub-category, region and segment fixed, each extra 10 points of discount goes with "
                        f"{da['slope_pp_per_10pt_discount_controlled']}pp of line margin (95% CI "
                        f"{da['slope_ci95_controlled'][0]} to {da['slope_ci95_controlled'][1]}). The dataset is a synthetic "
                        "Tableau sample, so this describes the sample, not a real retailer.",
         "action": "Cap discounts at 20% unless a test shows the extra volume pays for itself."},
        {"area": "Where to focus", "type": "Descriptive",
         "finding": f"{c['unprofitable_products']} of {c['products']} products lose money in total "
                    f"(${-c['unprofitable_products_loss']:,.0f}, {c['loss_as_pct_of_total_profit']}% of total profit). "
                    f"{len(c['loss_making_states'])} states/provinces are loss-making overall, led by "
                    f"{', '.join(c['loss_making_states'][:3])}; {central.region} has the lowest margin ({central.m:.1f}%).",
         "uncertainty": "Product-level losses mix discounting, shipping and pricing; the data has no separate cost lines.",
         "action": "Start a price/discount review with the top 20 loss-making products and the 3 worst states."},
        {"area": "What to expect next", "type": "Forecast",
         "finding": f"Holt-Winters (best monthly holdout error) projects ${f['next_12_months_total']:,.0f} revenue for the next 12 months.",
         "uncertainty": f"On the {f['test'][0][:4]} holdout it missed months by {hw['mape_pct']}% on average and undershot the "
                        f"year by {-hw['annual_total_error_pct']}%; SARIMA was worse month to month ({sa['mape_pct']}%) "
                        f"but within {sa['annual_total_error_pct']}% on the annual total.",
         "action": f"Use the forecast for seasonal planning ({peak_text}), not for a precise budget."},
    ]


def run() -> list[dict]:
    rows = build()
    pd.DataFrame(rows).to_csv(config.TABLEAU_DIR / "insights.csv", index=False)
    (config.RESULTS_DIR / "insights.json").write_text(json.dumps(rows, indent=2))
    return rows


if __name__ == "__main__":
    for r in run():
        print(f"[{r['area']}] {r['finding']}\n    {r['uncertainty']}\n    -> {r['action']}\n")
