import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app import ui
from retailpulse import forecast_daily

ui.page("Monitor", "Anomalies",
        "Days and months that broke their usual pattern, ranked by severity. The context shows what moved alongside "
        "each one. It describes the data and does not diagnose a cause.")

data = ui.results("anomalies.json")
source = st.segmented_control("Source", ["Online Retail II · daily", "Superstore · monthly"],
                              default="Online Retail II · daily") or "Online Retail II · daily"
uci = source.startswith("Online")
found = [a for a in data["anomalies"] if a["source"] == ("uci" if uci else "superstore")]

if uci:
    s = ui.snap("uci_daily").set_index("day")["net_revenue"].asfreq("D", fill_value=0)
    s = s[~forecast_daily.closed(s.index) & (s.index.day_of_week != 5)]      # trading days only, as scored
    metric, fmt, title = "net_revenue", "£%{y:,.0f}", "Daily net revenue, trading days"
else:
    metric = st.radio("Metric", ["revenue", "profit", "margin"], horizontal=True, format_func=str.title)
    d = ui.snap("superstore_daily").set_index("day")[["revenue", "profit"]].resample("MS").sum()
    s = d["profit"] / d["revenue"] * 100 if metric == "margin" else d[metric]
    fmt = "%{y:.1f}%" if metric == "margin" else "$%{y:,.0f}"
    title = f"Monthly {metric}"
    found = [a for a in found if a["metric"] == metric]

ui.section(title, "real" if uci else "synthetic")
counts = {k: sum(a["severity"] == k for a in found) for k in ("severe", "high", "moderate")}
ui.cards(*[ui.card(k.title(), str(v), None, None, f"|z| ≥ {c}") for (k, v), c in zip(counts.items(), (6, 5, 4))])

fig = go.Figure()
fig.add_scatter(x=s.index, y=s.values, name="Actual", line=dict(color=ui.SLATE, width=1.4),
                hovertemplate=f"%{{x|%d %b %Y}}: {fmt}<extra></extra>")
for sev, color in ui.SEVERITY_COLORS.items():
    pts = [a for a in found if a["severity"] == sev]
    if pts:
        x = pd.to_datetime([a["period"] for a in pts])
        y = [s.get(t, None) for t in x]
        fig.add_scatter(x=x, y=y, mode="markers", name=sev.title(),
                        marker=dict(size=13, color=color, line=dict(color="white", width=2), symbol="diamond"),
                        customdata=[[a["expected"] * (100 if metric == "margin" else 1), a["z"]] for a in pts],
                        hovertemplate=f"%{{x|%d %b %Y}}: {fmt}<br>expected %{{customdata[0]:,.1f}} · "
                                      f"z %{{customdata[1]:+.1f}}<extra>{sev}</extra>")
fig.update_layout(title=title, height=380, yaxis=dict(tickformat="~s"))
st.plotly_chart(fig, width="stretch")


def describe(a: dict) -> str:
    c = a["context"]
    if a["source"] == "uci":
        bits = [f"{c['invoices']} invoices", f"largest invoice {c['largest_invoice_share_pct']}% of the day "
                f"({c['largest_invoice_country']})"]
        if c["cancelled_value"] < -1000:
            bits.append(f"£{-c['cancelled_value']:,.0f} cancelled")
        if c["within_3_days_of_known_closure"]:
            bits.append("within 3 days of a known closure")
        return "; ".join(bits)
    if "note" in c:
        return c["note"]
    moves = ", ".join(f"{k} {ui.signed(v, unit='$')}" for k, v in c["largest_profit_changes"].items())
    return f"largest profit changes vs {c['vs'][:7]}: {moves}"


if found:
    ui.section("Flagged periods")
    st.dataframe(pd.DataFrame([{"Period": a["period"], "Severity": a["severity"].title(), "Actual": a["actual"],
                                "Expected": a["expected"], "z": a["z"], "What moved with it": describe(a)}
                               for a in sorted(found, key=lambda a: -abs(a["z"]))]),
                 hide_index=True, width="stretch",
                 column_config={"Actual": st.column_config.NumberColumn(format="%,.2f"),
                                "Expected": st.column_config.NumberColumn(format="%,.2f"),
                                "z": st.column_config.NumberColumn(format="%+.1f")})
else:
    ui.callout("Nothing flagged", "No period reached the moderate threshold for this series.", "good")

with st.expander("Method and calibration"):
    st.markdown("""
- **Online Retail II (daily).** Each trading day's revenue against the median of the same weekday over the previous
  8 weeks, on a log scale, divided by the robust spread of that ratio over the previous 60 trading days. It only
  looks backwards, so it could run every morning.
- **Superstore (monthly).** Each month against its year's level plus the calendar-month pattern of the *other* three
  years. That keeps a month from hiding in its own expected value.
- **Severity.** Robust z of 4, 5 and 6 or more. Calibrated by simulation: on noise-only data under 1% of months reach 4
  (2.6% would reach 3). A test enforces this.
- **Context, not cause.** Sub-category moves, invoice concentration, cancellations and closures are listed because
  they moved together with the anomaly. Explaining one needs someone who knows the business.
""")
