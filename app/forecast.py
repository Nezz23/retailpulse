import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app import ui

ui.page("Monitor", "Demand forecast",
        "Daily net product revenue for the next 30, 60 and 90 days, chosen by a rolling-origin backtest against "
        "naive baselines. Each backtest fold sees only the days before its origin.", "real")

fc = ui.results("uci_forecast.json")
f = ui.forecast_frame().set_index("day")
names = {"naive_weekly": "Weekly naive (baseline)", "naive_last_year": "Same weekday last year",
         "holt_winters": "Holt-Winters", "sarimax_fourier": "SARIMAX + annual terms",
         "combination": "SARIMAX / last-year blend"}

h = st.segmented_control("Horizon", [30, 60, 90], default=90, format_func=lambda d: f"{d} days") or 90
t = fc["totals"][f"next_{h}_days"]
s_best, s_base = fc["scores"][fc["selected"]][str(h)], fc["scores"][fc["baseline"]][str(h)]

ui.cards(
    ui.card(f"Next {h} days", f"£{t['forecast'] / 1e6:,.2f}M", None, None, f"from {fc['forecast_start']}"),
    ui.card("Backtest range", f"£{t['backtest_low'] / 1e6:,.2f}M – £{t['backtest_high'] / 1e6:,.2f}M", None, None,
            "the selected model's own past errors"),
    ui.card("Daily WAPE", f"{s_best['wape_pct']:.1f}%", f"−{s_base['wape_pct'] - s_best['wape_pct']:.1f} pts", True,
            "vs weekly naive baseline"),
    ui.card("80% interval coverage", f"{s_best['coverage80_pct']:.0f}%", None, None,
            f"95% interval: {s_best['coverage95_pct']:.0f}%"),
)

hist = f["actual"].dropna().iloc[-120:]
ahead = f[f["forecast"].notna()].iloc[:h]
fig = go.Figure()
fig.add_scatter(x=ahead.index.tolist() + ahead.index[::-1].tolist(),
                y=ahead["hi95"].tolist() + ahead["lo95"][::-1].tolist(), fill="toself", name="95% interval",
                fillcolor="rgba(42,99,214,0.10)", line=dict(width=0), hoverinfo="skip")
fig.add_scatter(x=ahead.index.tolist() + ahead.index[::-1].tolist(),
                y=ahead["hi80"].tolist() + ahead["lo80"][::-1].tolist(), fill="toself", name="80% interval",
                fillcolor="rgba(42,99,214,0.20)", line=dict(width=0), hoverinfo="skip")
fig.add_scatter(x=hist.index, y=hist.values, name="Actual", line=dict(color=ui.SLATE, width=1.6),
                hovertemplate="%{x|%a %d %b %Y}: £%{y:,.0f}<extra></extra>")
fig.add_scatter(x=ahead.index, y=ahead["forecast"], name="Forecast", line=dict(color=ui.BLUE, width=2.2),
                hovertemplate="%{x|%a %d %b %Y}: £%{y:,.0f}<extra></extra>")
fig.update_layout(title=f"Daily net revenue: last 120 days and next {h}", height=420,
                  yaxis=dict(tickprefix="£", tickformat="~s"))
st.plotly_chart(fig, width="stretch")
st.caption("Zero days are Saturdays, bank holidays and the Christmas shutdown (Dec 24 – Jan 3). The forecast "
           "knows this calendar; it is verified against every closed day in the data.")

ui.section("How the models compared")
c1, c2 = st.columns([1, 1.2])
with c1:
    rows = pd.DataFrame([{"model": names[m], "wape": v[str(h)]["wape_pct"], "key": m} for m, v in fc["scores"].items()])
    rows = rows.sort_values("wape")
    fig = go.Figure(go.Bar(
        x=rows["wape"], y=rows["model"], orientation="h", text=[f"{v:.1f}%" for v in rows["wape"]],
        textposition="outside", hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
        marker_color=[ui.BLUE if k == fc["selected"] else (ui.ORANGE if k == fc["baseline"] else "#c8d0e0")
                      for k in rows["key"]]))
    fig.update_layout(title=f"Backtest WAPE, {h}-day horizon (lower is better)", height=320,
                      xaxis=dict(ticksuffix="%", range=[0, rows["wape"].max() * 1.25]),
                      yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")
with c2:
    tbl = pd.DataFrame([{"Model": names[m], **{k: v[str(h)][k] for k in
                         ("wape_pct", "total_error_pct", "coverage80_pct", "coverage95_pct")},
                         "Year-end fold WAPE": fc["year_end_fold"][m]["wape_pct"]} for m, v in fc["scores"].items()])
    st.dataframe(tbl, hide_index=True, width="stretch", column_config={
        "wape_pct": st.column_config.NumberColumn("WAPE", format="%.1f%%"),
        "total_error_pct": st.column_config.NumberColumn("Bias on total", format="%+.1f%%"),
        "coverage80_pct": st.column_config.NumberColumn("80% cover", format="%.0f%%"),
        "coverage95_pct": st.column_config.NumberColumn("95% cover", format="%.0f%%"),
        "Year-end fold WAPE": st.column_config.NumberColumn(format="%.1f%%")})
    ui.callout("Why a blend",
               f"SARIMAX tracks the recent level best, but across New Year it overshot the total by "
               f"{fc['year_end_fold']['sarimax_fourier']['total_error_pct']:.0f}%: it carries the "
               "November peak into January. Same-weekday-last-year knows the post-Christmas drop. Their equal-weight "
               f"blend had the lowest error overall and on the year-end fold. Selection rule: "
               f"{fc['selection_rule']}.", "info")

with st.expander("Validation design and limits"):
    st.markdown(f"""
- **Rolling origin.** {len(fc['backtest']['origins'])} origins, 28 days apart ({fc['backtest']['origins'][0]} to
  {fc['backtest']['origins'][-1]}). Each model is refit on the days up to its origin only and scored on the next 90.
  A test checks that changing any later day leaves the forecast unchanged.
- **Metrics.** WAPE (sum of absolute errors over actual revenue), bias of the horizon total, and how often actual days
  fall inside the 80% and 95% intervals. MAPE is undefined on closed days.
- **Backtest range** for the totals is the min–max of the selected model's own total errors across folds (11 folds,
  overlapping, so it is a rough range, not a confidence interval).
- **Limits.** Two years of history, one year-end in the backtest, no promotions or prices as inputs, and the data
  ends in December 2011.
""")
