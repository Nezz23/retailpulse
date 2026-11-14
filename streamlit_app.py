"""RetailPulse decision app. Entry point for `streamlit run streamlit_app.py` and Streamlit Community Cloud."""
import streamlit as st

from app.ui import TABLEAU_URL

st.set_page_config(page_title="RetailPulse", page_icon=":material/insights:", layout="wide",
                   initial_sidebar_state="expanded")

nav = st.navigation({
    "Decide": [st.Page("app/overview.py", title="Executive overview", icon=":material/space_dashboard:", default=True),
               st.Page("app/simulator.py", title="Discount simulator", icon=":material/tune:")],
    "Monitor": [st.Page("app/forecast.py", title="Demand forecast", icon=":material/trending_up:"),
                st.Page("app/anomalies.py", title="Anomalies", icon=":material/notifications_active:"),
                st.Page("app/weekly_report.py", title="Weekly report", icon=":material/summarize:")],
    "Reference": [st.Page("app/methods.py", title="Data & methods", icon=":material/menu_book:")],
})

with st.sidebar:
    st.markdown("### RetailPulse\n<span style='font-size:13px;opacity:.75'>Retail decision intelligence</span>",
                unsafe_allow_html=True)
    st.link_button("Tableau executive dashboard", TABLEAU_URL, icon=":material/open_in_new:", width="stretch")
    st.caption("Superstore is synthetic. Online Retail II is real 2009–2011 data, replayed as a simulated feed. "
               "Modeled figures are estimates, not realized results.")

nav.run()
