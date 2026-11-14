import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app import ui

ui.page("Executive overview", "Where profit leaks, and what demand does next",
        "Two sources, kept apart: a synthetic store with full cost data for profitability decisions, and a real UK "
        "online retailer's transactions for demand. Every number below is computed from the data in this repository.")

# ---------------- Superstore: profitability ----------------
ui.section("Profitability · Superstore", "synthetic")
d = ui.snap("superstore_daily")
y = d.groupby(d["day"].dt.year)[["revenue", "profit", "deep_discount_profit", "deep_discount_revenue"]].sum()
cur, prev = y.index.max(), y.index.max() - 1
m_cur, m_prev = 100 * y.loc[cur, "profit"] / y.loc[cur, "revenue"], 100 * y.loc[prev, "profit"] / y.loc[prev, "revenue"]
mc = ui.results("analysis.json")["margin_change"][-1]
rec = ui.results("scenarios.json")["recommended"]["blanket"]
caps = pd.DataFrame(ui.results("scenarios.json")["blanket_caps"])
cap_rng = caps[caps["cap"] == rec["cap"]]["profit_change"]

ui.cards(
    ui.card(f"Revenue {cur}", f"${y.loc[cur, 'revenue'] / 1e3:,.1f}K",
            f"{ui.signed(100 * (y.loc[cur, 'revenue'] / y.loc[prev, 'revenue'] - 1), '{:.1f}')}%", True, f"vs {prev}"),
    ui.card(f"Profit {cur}", f"${y.loc[cur, 'profit'] / 1e3:,.1f}K",
            f"{ui.signed(100 * (y.loc[cur, 'profit'] / y.loc[prev, 'profit'] - 1), '{:.1f}')}%", True, f"vs {prev}"),
    ui.card("Profit margin", f"{m_cur:.2f}%", f"{ui.signed(m_cur - m_prev, '{:.2f}')} pp", False,
            f"95% CI {mc['ci95_pp'][0]:+.1f} to {mc['ci95_pp'][1]:+.1f} pp: not significant"),
    ui.card("Lost on deep discounts", f"${-y.loc[cur, 'deep_discount_profit'] / 1e3:,.1f}K", None, None,
            f"lines >20% off, {100 * y.loc[cur, 'deep_discount_revenue'] / y.loc[cur, 'revenue']:.0f}% of revenue"),
)

c1, c2 = st.columns([1.35, 1])
with c1:
    mo = d.set_index("day")["revenue"].resample("MS").sum()
    fig = go.Figure()
    for i, (yr, part) in enumerate(mo.groupby(mo.index.year)):
        fig.add_scatter(x=part.index.month, y=part.values, name=str(yr), mode="lines+markers",
                        line=dict(width=2.5 if yr == cur else 1.6, color=ui.BLUE if yr == cur else None),
                        marker=dict(size=6 if yr == cur else 4),
                        hovertemplate=f"{yr} %{{x}}: $%{{y:,.0f}}<extra></extra>")
    fig.update_layout(title="Monthly revenue by year", height=340, colorway=["#c8d0e0", "#a9b4cc", ui.SLATE, ui.BLUE],
                      xaxis=dict(tickmode="array", tickvals=list(range(1, 13)),
                                 ticktext=pd.date_range("2026-01-01", periods=12, freq="MS").strftime("%b")),
                      yaxis=dict(tickprefix="$", tickformat="~s"))
    st.plotly_chart(fig, width="stretch")
with c2:
    lines = ui.snap("superstore_lines_latest")
    lvl = lines.groupby("discount")[["sales", "profit"]].sum()
    m = 100 * lvl["profit"] / lvl["sales"]
    fig = go.Figure(go.Bar(x=[f"{v:.0%}" for v in m.index], y=m.values,
                           marker_color=[ui.BLUE if v >= 0 else ui.ORANGE for v in m.values],
                           hovertemplate="Discount %{x}<br>Margin %{y:.1f}%<extra></extra>"))
    fig.update_layout(title=f"Margin by discount level, {cur}", height=340, yaxis=dict(ticksuffix="%"),
                      bargap=0.35)
    fig.add_hline(y=0, line_color=ui.MUTED, line_width=1)
    st.plotly_chart(fig, width="stretch")

ui.callout(f"Recommendation: cap discounts at {rec['cap']:.0%} and roll it out as a controlled test",
           f"Every discount level above {rec['cap']:.0%} lost money in {cur}. A {rec['cap']:.0%} cap is modeled at "
           f"<b>+${cap_rng.min() / 1e3:,.1f}K to +${cap_rng.max() / 1e3:,.1f}K</b> profit a year, depending on how much "
           f"of the capped volume walks away. This is a <b>modeled opportunity, not a realized saving</b>; "
           f"test it in the Discount simulator.", "good")

# ---------------- Online Retail II: demand ----------------
ui.section("Demand · Online Retail II", "real")
u = ui.snap("uci_daily").set_index("day")["net_revenue"]
fc = ui.results("uci_forecast.json")
end = pd.Timestamp(fc["history"][1])
last12, prev12 = u.loc[end - pd.Timedelta(days=364):end].sum(), u.loc[end - pd.Timedelta(days=728):end - pd.Timedelta(days=365)].sum()
t90 = fc["totals"]["next_90_days"]
an = [a for a in ui.results("anomalies.json")["anomalies"] if a["source"] == "uci"]
ui.cards(
    ui.card("Net revenue, last 52 weeks", f"£{last12 / 1e6:,.2f}M", f"{ui.signed(100 * (last12 / prev12 - 1), '{:.1f}')}%",
            last12 >= prev12, "vs prior 52 weeks"),
    ui.card("Next 90 days (forecast)", f"£{t90['forecast'] / 1e6:,.2f}M", None, None,
            f"backtest range £{t90['backtest_low'] / 1e6:.2f}M–£{t90['backtest_high'] / 1e6:.2f}M"),
    ui.card("Forecast accuracy gain", f"{fc['beats_baseline_pct']:.1f} pts", None, None,
            "lower 90-day WAPE than a weekly naive baseline"),
    ui.card("Anomalous trading days", f"{len(an)}", None, None,
            f"{sum(a['severity'] == 'severe' for a in an)} severe · trailing same-weekday baseline"),
)
f = ui.forecast_frame().set_index("day")
hist = u.resample("W-SUN").sum().loc[:end - pd.Timedelta(days=end.day_of_week + 1)]
ahead = f["forecast"].dropna().resample("W-SUN").sum()
fig = go.Figure()
fig.add_scatter(x=hist.index, y=hist.values, name="Actual", line=dict(color=ui.SLATE, width=2),
                hovertemplate="Week to %{x|%d %b %Y}: £%{y:,.0f}<extra></extra>")
fig.add_scatter(x=ahead.index, y=ahead.values, name="Forecast", line=dict(color=ui.BLUE, width=2.5, dash="dot"),
                hovertemplate="Week to %{x|%d %b %Y}: £%{y:,.0f}<extra></extra>")
fig.update_layout(title="Weekly net revenue and the next 90 days", height=320, yaxis=dict(tickprefix="£", tickformat="~s"))
st.plotly_chart(fig, width="stretch")
st.caption("Partial weeks at the edges of the forecast are expected to look low. Details in Demand forecast.")

ui.footer("Superstore: Tableau Sample Superstore (synthetic). Online Retail II: Chen (2012), UCI ML Repository, CC BY "
          "4.0. Associations are not causes; modeled figures are estimates.")
