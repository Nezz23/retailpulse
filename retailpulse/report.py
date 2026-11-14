"""Weekly executive report: KPIs, forecast, anomalies and recommendations, as one self-contained HTML file.

Reads only results/ (JSON outputs and snapshots), so it runs anywhere, including the scheduled GitHub Action.
Both datasets are historical, so "this week" is the latest complete Monday-Sunday week in each source unless set:

    python -m retailpulse.report                                    # latest complete weeks
    REPORT_UCI_WEEK=2011-11-27 REPORT_SUPERSTORE_WEEK=2026-11-29 python -m retailpulse.report
    REPORT_OUT_DIR=/tmp/reports python -m retailpulse.report
"""
import html
import json
import os
from pathlib import Path

import pandas as pd

from . import config, snapshot

TABLEAU_URL = ("https://public.tableau.com/app/profile/neha.kothavade/viz/"
               "RetailPulse_ExecutiveOverview_approved/ExecutiveOverview")


def _json(name: str) -> dict:
    return json.loads((config.RESULTS_DIR / name).read_text())


def daily(name: str) -> pd.DataFrame:
    df = pd.read_csv(snapshot.DIR / f"{name}.csv", parse_dates=["day"])
    return df.set_index("day").asfreq("D", fill_value=0)


def week_end(df: pd.DataFrame, override: str | None) -> pd.Timestamp:
    """The Sunday ending the chosen week; by default the last week the data fully covers."""
    if override:
        return pd.Timestamp(override)
    last = df.index.max()
    return last if last.day_of_week == 6 else last - pd.Timedelta(days=last.day_of_week + 1)


def week(df: pd.DataFrame, end: pd.Timestamp, weeks_back: int = 0) -> pd.DataFrame:
    e = end - pd.Timedelta(weeks=weeks_back)
    return df.loc[e - pd.Timedelta(days=6):e]


def pct(a: float, b: float) -> float | None:
    return None if not b else 100 * (a / b - 1)


def superstore_section(end: pd.Timestamp) -> dict:
    d = daily("superstore_daily")
    cur, prev, ly = week(d, end), week(d, end, 1), week(d, end, 52)
    rev, prof = cur["revenue"].sum(), cur["profit"].sum()
    trail = d.loc[end - pd.Timedelta(weeks=13):end - pd.Timedelta(days=7)]
    kpis = {"Revenue": (rev, pct(rev, prev["revenue"].sum()), pct(rev, ly["revenue"].sum()), "$"),
            "Profit": (prof, pct(prof, prev["profit"].sum()), pct(prof, ly["profit"].sum()), "$"),
            "Margin": (100 * prof / rev if rev else None, None, None, "%"),
            "Orders": (cur["orders"].sum(), pct(cur["orders"].sum(), prev["orders"].sum()),
                       pct(cur["orders"].sum(), ly["orders"].sum()), "")}
    recs = []
    deep_loss, deep_rev = cur["deep_discount_profit"].sum(), cur["deep_discount_revenue"].sum()
    if deep_loss < 0:
        sc = _json("scenarios.json")["blanket_caps"]
        cap20 = [s["profit_change"] for s in sc if s["cap"] == 0.2]
        recs.append(f"Lines discounted above 20% lost ${-deep_loss:,.0f} this week on ${deep_rev:,.0f} of revenue "
                    f"({100 * deep_rev / rev:.0f}% of the week). The 20% discount cap is modeled at "
                    f"+${min(cap20):,.0f} to +${max(cap20):,.0f} a year; run it as the controlled test in "
                    f"docs/discount_business_case.md.")
    if rev and trail["revenue"].sum() and 100 * prof / rev < 100 * trail["profit"].sum() / trail["revenue"].sum() - 2:
        recs.append(f"Margin {100 * prof / rev:.1f}% is more than 2 points below the previous 12 weeks "
                    f"({100 * trail['profit'].sum() / trail['revenue'].sum():.1f}%). Check which discount levels "
                    f"and sub-categories carried the week before changing prices.")
    return {"title": "Superstore", "badge": "synthetic data", "week": end, "kpis": kpis, "recs": recs,
            "anomalies": _recent_anomalies("superstore", end, weeks=26)}


def uci_section(end: pd.Timestamp) -> dict:
    d = daily("uci_daily")
    cur, prev, ly = week(d, end), week(d, end, 1), week(d, end, 52)
    rev = cur["net_revenue"].sum()
    gross, cancelled = cur["gross_revenue"].sum(), -cur["cancelled_revenue"].sum()
    weekly = d.resample("W-SUN")[["gross_revenue", "cancelled_revenue"]].sum()
    typical = (-weekly["cancelled_revenue"] / weekly["gross_revenue"]).loc[:end - pd.Timedelta(days=7)].median()
    kpis = {"Net revenue": (rev, pct(rev, prev["net_revenue"].sum()), pct(rev, ly["net_revenue"].sum()), "£"),
            "Invoices": (cur["invoices"].sum(), pct(cur["invoices"].sum(), prev["invoices"].sum()),
                         pct(cur["invoices"].sum(), ly["invoices"].sum()), ""),
            "Cancelled": (cancelled, pct(cancelled, -prev["cancelled_revenue"].sum()), None, "£"),
            "Cancellation rate": (100 * cancelled / gross if gross else None, None, None, "%")}
    recs = []
    if gross and cancelled / gross > 2 * typical:
        recs.append(f"Cancellations were {100 * cancelled / gross:.1f}% of gross sales, against a typical "
                    f"{100 * typical:.1f}% a week. Review the largest cancelled invoices before reading the week "
                    f"as weaker demand.")
    yoy = pct(rev, ly["net_revenue"].sum())
    if yoy is not None and yoy < -15:
        recs.append(f"Net revenue is {-yoy:.0f}% below the same week last year. Compare against the forecast "
                    f"range before acting; a single week moves a lot (daily backtest WAPE about 30%).")
    section = {"title": "Online Retail II", "badge": "real data, simulated feed", "week": end, "kpis": kpis,
               "recs": recs, "anomalies": _recent_anomalies("uci", end, weeks=8)}
    fc = _json("uci_forecast.json")
    if end >= pd.Timestamp(fc["history"][1]) - pd.Timedelta(days=7):     # a back-dated report gets no later forecast
        section["forecast"] = {"made_on": fc["history"][1], "model": fc["selected"],
                               "beats_baseline_pts": fc["beats_baseline_pct"], "totals": fc["totals"]}
        t90 = fc["totals"]["next_90_days"]
        recs.append(f"Plan stock and staffing for £{t90['forecast'] / 1e6:.2f}M of net revenue over the 90 days "
                    f"after {fc['history'][1]} (backtest range £{t90['backtest_low'] / 1e6:.2f}M to "
                    f"£{t90['backtest_high'] / 1e6:.2f}M).")
    return section


def _recent_anomalies(source: str, end: pd.Timestamp, weeks: int) -> list[dict]:
    start = end - pd.Timedelta(weeks=weeks)
    return [a for a in _json("anomalies.json")["anomalies"]
            if a["source"] == source and start < pd.Timestamp(a["period"]) <= end]


def _fmt(v, unit: str) -> str:
    if v is None:
        return "–"
    if unit == "%":
        return f"{v:.1f}%"
    return f"{unit}{v:,.0f}"


def _delta(v) -> str:
    if v is None:
        return '<span class="muted">–</span>'
    cls = "up" if v >= 0 else "down"
    return f'<span class="{cls}">{"▲" if v >= 0 else "▼"} {abs(v):.1f}%</span>'


def render(sections: list[dict]) -> str:
    e = html.escape
    parts = []
    for s in sections:
        cards = "".join(f'<div class="card"><div class="label">{e(k)}</div><div class="value">{_fmt(v, u)}</div>'
                        f'<div class="deltas">WoW {_delta(w)} · YoY {_delta(y)}</div></div>'
                        for k, (v, w, y, u) in s["kpis"].items())
        recs = "".join(f"<li>{e(r)}</li>" for r in s["recs"]) or "<li>No rule fired this week.</li>"
        rows = "".join(f'<tr><td>{e(a["period"])}</td><td>{e(a["metric"])}</td><td>{a["actual"]:,.2f}</td>'
                       f'<td>{a["expected"]:,.2f}</td><td>{a["z"]:+.1f}</td>'
                       f'<td><span class="sev {e(a["severity"])}">{e(a["severity"])}</span></td></tr>'
                       for a in s["anomalies"])
        anomalies = (f"<table><tr><th>Period</th><th>Metric</th><th>Actual</th><th>Expected</th><th>z</th>"
                     f"<th>Severity</th></tr>{rows}</table>") if rows else '<p class="muted">None flagged.</p>'
        fc = ""
        if "forecast" in s:
            f = s["forecast"]
            fc = ("<h3>Forecast</h3><table><tr><th>Horizon</th><th>Forecast</th><th>Backtest range</th></tr>" + "".join(
                f'<tr><td>{k.replace("_", " ")}</td><td>£{v["forecast"]:,.0f}</td>'
                f'<td>£{v["backtest_low"]:,.0f} – £{v["backtest_high"]:,.0f}</td></tr>' for k, v in f["totals"].items())
                + f'</table><p class="muted">Made on data to {e(f["made_on"])}; model {e(f["model"])}, '
                  f'{f["beats_baseline_pts"]:.1f} points lower 90-day WAPE than the weekly naive baseline.</p>')
        week_start = (s["week"] - pd.Timedelta(days=6)).strftime("%d %b")
        parts.append(f'<section><h2>{e(s["title"])} <span class="badge">{e(s["badge"])}</span></h2>'
                     f'<p class="muted">Week {week_start} – {s["week"].strftime("%d %b %Y")}</p>'
                     f'<div class="cards">{cards}</div><h3>Recommendations</h3><ul>{recs}</ul>{fc}'
                     f'<h3>Recent anomalies</h3>{anomalies}</section>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>RetailPulse weekly report</title><style>
body{{font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;color:#0f1f3d;background:#f5f7fb;margin:0;padding:24px}}
main{{max-width:880px;margin:auto}} h1{{margin:0 0 4px}} h2{{margin:32px 0 0}} h3{{margin:24px 0 8px;font-size:15px}}
section{{background:#fff;border:1px solid #e3e6ec;border-radius:12px;padding:8px 24px 24px;margin-top:20px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:12px}}
.card{{border:1px solid #e3e6ec;border-radius:10px;padding:12px}} .label{{color:#5b6475;font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
.value{{font-size:24px;font-weight:700}} .deltas{{font-size:12px;color:#5b6475}} .up{{color:#1a7f4e}} .down{{color:#c2410c}}
.muted{{color:#5b6475;font-size:13px}} .badge{{font-size:12px;font-weight:500;background:#eef2ff;color:#3730a3;border-radius:99px;padding:2px 10px;vertical-align:middle}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #eef0f4}}
.sev{{border-radius:6px;padding:1px 8px;font-size:12px}} .moderate{{background:#fef3c7}} .high{{background:#fed7aa}} .severe{{background:#fecaca}}
</style></head><body><main><h1>RetailPulse weekly report</h1>
<p class="muted">Superstore is synthetic; Online Retail II is real 2009–2011 data replayed as a simulated feed. Anomaly
context and recommendations describe the data; they do not diagnose causes. Interactive dashboard:
<a href="{TABLEAU_URL}">Tableau Public</a>.</p>{"".join(parts)}</main></body></html>"""


def run() -> Path:
    out_dir = Path(os.environ.get("REPORT_OUT_DIR", config.ROOT / "reports"))
    ss = superstore_section(week_end(daily("superstore_daily"), os.environ.get("REPORT_SUPERSTORE_WEEK")))
    uc = uci_section(week_end(daily("uci_daily"), os.environ.get("REPORT_UCI_WEEK")))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"weekly_{uc['week'].date()}_{ss['week'].date()}.html"
    path.write_text(render([uc, ss]))
    return path


if __name__ == "__main__":
    print(run())
