import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app import ui
from retailpulse import scenarios

ui.page("Decide", "Discount cap simulator",
        "Reprice every order line discounted above a cap, decide how much of that volume you expect to lose, and see "
        "the effect on revenue, profit and margin against the actual year.", "modeled")

lines = ui.snap("superstore_lines_latest")
subs = sorted(lines["sub_category"].unique())
base_rev, base_profit = lines["sales"].sum(), lines["profit"].sum()

with st.container(border=True):
    c1, c2, c3 = st.columns([1, 1, 1.4])
    cap = c1.slider("Maximum discount", 0.05, 0.40, 0.20, 0.05, format="%.2f",
                    help="Lines discounted above this are repriced to list price × (1 − cap).")
    loss = c2.slider("Demand lost on capped lines", 0, 100, 25, 5, format="%d%%",
                     help="Share of the capped lines' volume that no longer sells. 100% = those lines are not sold.") / 100
    scope = c3.multiselect("Apply to sub-categories (empty = all)", subs, placeholder="All sub-categories")

r = scenarios.cap(lines, cap, loss, scope or None)
r0 = scenarios.cap(lines, cap, 0.0, scope or None)
base_m = 100 * base_profit / base_rev

ui.cards(
    ui.card("Revenue", f"${r['revenue'] / 1e3:,.1f}K", f"{ui.signed(r['revenue_change'] / 1e3, '{:,.1f}', '$')}K",
            r["revenue_change"] >= 0, f"baseline ${base_rev / 1e3:,.1f}K"),
    ui.card("Profit", f"${r['profit'] / 1e3:,.1f}K", f"{ui.signed(r['profit_change'] / 1e3, '{:,.1f}', '$')}K",
            r["profit_change"] >= 0, f"baseline ${base_profit / 1e3:,.1f}K"),
    ui.card("Margin", f"{r['margin_pct']:.2f}%", f"{ui.signed(r['margin_change_pp'], '{:.2f}')} pp",
            r["margin_change_pp"] >= 0, f"baseline {base_m:.2f}%"),
    ui.card("Lines capped", f"{r['lines_capped']:,}", None, None,
            f"their profit today: ${r['capped_lines_baseline_profit'] / 1e3:,.1f}K"),
)

if r["lines_capped"] == 0:
    ui.callout("No line is discounted above this cap", "The scenario equals the baseline.", "info")
elif r["only_loss_making_levels"]:
    ui.callout("No-regret cap", f"Every discount level this cap touches loses money today, so profit cannot fall "
               f"whatever share of that volume is lost. Worst case (all of it lost): "
               f"<b>{ui.signed(-r['capped_lines_baseline_profit'] / 1e3, '{:,.1f}', '$')}K</b>.", "good")
else:
    ui.callout("This cap also reaches discount levels that are profitable today",
               "The gain rests on customers accepting higher prices. Check the curve below: the more demand "
               "you lose, the faster the gain shrinks.", "warn")

c1, c2 = st.columns(2)
with c1:
    price, volume = r0["profit_change"], r["profit_change"] - r0["profit_change"]
    fig = go.Figure(go.Waterfall(
        x=["Baseline profit", "Price recovery", "Lost volume", "Scenario profit"],
        measure=["absolute", "relative", "relative", "total"], y=[base_profit, price, volume, 0],
        connector=dict(line=dict(color=ui.LINE)), increasing=dict(marker_color=ui.GREEN),
        decreasing=dict(marker_color=ui.ORANGE), totals=dict(marker_color=ui.BLUE),
        text=[f"${v / 1e3:,.1f}K" for v in (base_profit, price, volume, r["profit"])], textposition="outside",
        hovertemplate="%{x}: $%{y:,.0f}<extra></extra>"))
    fig.update_layout(title="Profit bridge, latest year", height=360, yaxis=dict(tickprefix="$", tickformat="~s"),
                      showlegend=False)
    st.plotly_chart(fig, width="stretch")
with c2:
    grid = range(0, 101, 5)
    fig = go.Figure()
    ref = 0.20
    if abs(cap - ref) > 1e-9:
        fig.add_scatter(x=list(grid), y=[scenarios.cap(lines, ref, g / 100, scope or None)["profit_change"] for g in grid],
                        name=f"{ref:.0%} cap (recommended)", line=dict(color=ui.SLATE, width=1.6, dash="dot"),
                        hovertemplate="%{x}% lost: $%{y:,.0f}<extra></extra>")
    fig.add_scatter(x=list(grid), y=[scenarios.cap(lines, cap, g / 100, scope or None)["profit_change"] for g in grid],
                    name=f"{cap:.0%} cap", line=dict(color=ui.BLUE, width=2.5),
                    hovertemplate="%{x}% lost: $%{y:,.0f}<extra></extra>")
    fig.add_scatter(x=[loss * 100], y=[r["profit_change"]], mode="markers", name="Your assumption",
                    marker=dict(size=12, color=ui.BLUE, line=dict(color="white", width=2)),
                    hovertemplate="%{x}% lost: $%{y:,.0f}<extra></extra>")
    fig.add_hline(y=0, line_color=ui.MUTED, line_width=1)
    fig.update_layout(title="Profit change vs demand lost", height=360, xaxis=dict(ticksuffix="%"),
                      yaxis=dict(tickprefix="$", tickformat="~s"))
    st.plotly_chart(fig, width="stretch")

ui.section("Every cap at your demand assumption")
table = pd.DataFrame([scenarios.cap(lines, c, loss, scope or None) for c in (0.10, 0.15, 0.20, 0.25, 0.30)])
st.dataframe(
    table[["cap", "lines_capped", "revenue_change", "profit_change", "margin_pct", "only_loss_making_levels"]],
    hide_index=True, width="stretch",
    column_config={"cap": st.column_config.NumberColumn("Cap", format="percent"),
                   "lines_capped": st.column_config.NumberColumn("Lines capped", format="%d"),
                   "revenue_change": st.column_config.NumberColumn("Revenue change", format="dollar"),
                   "profit_change": st.column_config.NumberColumn("Profit change", format="dollar"),
                   "margin_pct": st.column_config.NumberColumn("Margin", format="%.2f%%"),
                   "only_loss_making_levels": st.column_config.CheckboxColumn("No-regret")})

with st.expander("How the model works, and what it ignores"):
    st.markdown("""
- **Repricing.** A line above the cap is sold at list price × (1 − cap). Its cost (`sales − profit`) is unchanged.
- **Demand loss.** The chosen share of each capped line's volume disappears, taking its revenue and its cost with it.
  The same share applies to every capped line, although a line repriced from 80% to 20% off (a 4× price rise) would
  likely lose far more than one moving from 30% to 20%.
- **Not modeled:** basket and halo effects of loss leaders, competitor response, customers switching products.
- **Data:** the latest year of Superstore, which is **synthetic**. The discount-to-profit link is an association.
  A controlled test is how to measure the real effect. Full write-up: `docs/discount_business_case.md`.
""")
