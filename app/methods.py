import pandas as pd
import streamlit as st

from app import ui

ui.page("Reference", "Data & methods",
        "What each source is, what was done to it, and what it cannot tell you.")

st.dataframe(pd.DataFrame([
    {"Source": "Tableau Sample Superstore", "Type": "Synthetic", "Period": "2023–2026", "Grain": "Order line",
     "Used for": "Profitability, discounts, scenarios, monthly forecast, monthly anomalies",
     "Has cost / profit": "Yes (generated)"},
    {"Source": "UCI Online Retail II (Chen 2012, CC BY 4.0)", "Type": "Real", "Period": "Dec 2009 – Dec 2011",
     "Grain": "Invoice line", "Used for": "Daily demand forecast, daily anomalies, ingestion",
     "Has cost / profit": "No: no profit is derived"},
]), hide_index=True, width="stretch")

ui.section("Ingestion log · Online Retail II", "real")
st.markdown("Loaded **incrementally** into PostgreSQL by `python -m retailpulse.ingest`. This is a **simulated feed**: "
            "the 2009–2011 history is replayed in date windows, not streamed from a live store. A unique key over all "
            "eight fields rejects duplicates, each batch is one transaction, and the watermark only moves on success.")
log = ui.snap("uci_ingest_log")
st.dataframe(log[["batch_id", "window_start", "window_end", "rows_in", "rows_rejected", "rows_duplicate", "rows_new",
                  "status"]], hide_index=True, width="stretch")

ui.section("Limitations")
st.markdown("""
- **Synthetic profitability.** Superstore's discount-to-profit relationship may be built into its generator. It shows
  the method; it says nothing about real customers.
- **Association, not causation.** Deep discounts may follow weak products rather than cause losses. Discount caps are
  *modeled*; a controlled test measures them.
- **No cost in the real data.** Online Retail II has revenue only, so nothing about margin is claimed for it.
- **Short histories.** Four years of monthly Superstore data and two years of daily Online Retail II data limit both
  the forecast and the anomaly baselines.
- **Historical, not live.** Both sources end in the past. "This week" in reports means a chosen historical week.
""")
ui.footer("Code, tests and full write-ups: github.com/Nezz23/retailpulse · Tableau dashboard linked in the sidebar.")
