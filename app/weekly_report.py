import pandas as pd
import streamlit as st

from app import ui
from retailpulse import report

ui.page("Monitor", "Weekly executive report",
        "The same report the scheduled GitHub Action builds every Monday: KPIs, week-over-week and year-over-year, the "
        "latest forecast, recent anomalies and rule-based recommendations. Pick any historical week.")

uci_days, ss_days = report.daily("uci_daily"), report.daily("superstore_daily")
sundays = lambda d: [t for t in d.index if t.day_of_week == 6 and t - pd.Timedelta(days=6) >= d.index.min()][::-1]  # noqa: E731
c1, c2 = st.columns(2)
uci_week = c1.selectbox("Online Retail II week ending", sundays(uci_days), format_func=lambda t: t.strftime("%d %b %Y"))
ss_week = c2.selectbox("Superstore week ending", sundays(ss_days), format_func=lambda t: t.strftime("%d %b %Y"))

page = report.render([report.uci_section(uci_week), report.superstore_section(ss_week)])
st.download_button("Download HTML report", page, file_name=f"retailpulse_weekly_{uci_week.date()}_{ss_week.date()}.html",
                   mime="text/html", icon=":material/download:")
st.iframe(page, height=1500)   # our own escaped HTML, not user input
