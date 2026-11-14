"""Shared look and data access for the RetailPulse app: theme, KPI cards, callouts, cached loaders.
Everything reads precomputed files in results/, so the app needs no database."""
import html
import json

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from retailpulse import config, snapshot
from retailpulse.report import TABLEAU_URL  # noqa: F401  (re-exported for pages)

INK, MUTED, LINE = "#0f1f3d", "#5b6475", "#e6e9f0"
BLUE, SLATE, ORANGE, GREEN = "#2a63d6", "#8a97b4", "#e8590c", "#1a7f4e"
SEVERITY_COLORS = {"moderate": "#f2b705", "high": "#e8590c", "severe": "#c92a2a"}

pio.templates["retailpulse"] = go.layout.Template(layout=dict(
    font=dict(family="Inter, -apple-system, Segoe UI, sans-serif", color=INK, size=13),
    colorway=[BLUE, SLATE, ORANGE, GREEN], paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(gridcolor=LINE, linecolor=LINE, zeroline=False, ticks=""),
    yaxis=dict(gridcolor=LINE, linecolor=LINE, zeroline=False, ticks=""),
    margin=dict(l=8, r=8, t=44, b=8), hoverlabel=dict(bgcolor="white", font_size=12, bordercolor=LINE),
    title=dict(font=dict(size=15, color=INK), x=0, xanchor="left"),
    legend=dict(orientation="h", y=1.0, x=1, yanchor="bottom", xanchor="right", title_text="")))
pio.templates.default = "retailpulse"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stText { font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif; }
.block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1280px; }
h1, h2, h3 { letter-spacing: -0.02em; color: #0f1f3d; }
[data-testid="stSidebar"] { background: #0f1f3d; }
[data-testid="stSidebar"] * { color: #dfe5f2 !important; }
[data-testid="stSidebar"] a:hover { background: rgba(255,255,255,.08) !important; }
.rp-eyebrow { font-size: 12px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: #2a63d6; }
.rp-title { font-size: 30px; font-weight: 700; margin: 2px 0 2px; color: #0f1f3d; letter-spacing: -0.02em; }
.rp-sub { color: #5b6475; font-size: 15px; margin-bottom: 18px; max-width: 860px; }
.rp-badge { display:inline-block; font-size:11px; font-weight:600; border-radius:99px; padding:2px 10px; margin-left:8px;
            vertical-align: middle; letter-spacing:.02em; }
.rp-badge.real { background:#e7f5ee; color:#1a7f4e; } .rp-badge.synthetic { background:#eef2ff; color:#3949ab; }
.rp-badge.modeled { background:#fff4e6; color:#b45309; }
.rp-cards { display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin: 6px 0 18px; }
.rp-card { background:#fff; border:1px solid #e6e9f0; border-radius:14px; padding:16px 18px;
           box-shadow: 0 1px 2px rgba(15,31,61,.04); }
.rp-card .label { font-size:12px; color:#5b6475; font-weight:500; text-transform:uppercase; letter-spacing:.05em; }
.rp-card .value { font-size:26px; font-weight:700; color:#0f1f3d; margin-top:4px; letter-spacing:-0.02em; }
.rp-card .delta { font-size:13px; margin-top:2px; color:#5b6475; }
.rp-card .delta .good { color:#1a7f4e; font-weight:600; } .rp-card .delta .bad { color:#c2410c; font-weight:600; }
.rp-callout { border-radius:14px; padding:16px 20px; margin: 4px 0 18px; border:1px solid; }
.rp-callout.info { background:#f3f6fd; border-color:#d9e2f7; } .rp-callout.good { background:#effaf4; border-color:#cdebd9; }
.rp-callout.warn { background:#fff8ec; border-color:#f6dfb3; }
.rp-callout .head { font-weight:600; color:#0f1f3d; margin-bottom:2px; } .rp-callout .body { color:#33405a; font-size:14px; }
.rp-section { font-size:18px; font-weight:650; color:#0f1f3d; margin: 18px 0 6px; }
.rp-foot { color:#8a93a6; font-size:12px; margin-top: 28px; border-top:1px solid #e6e9f0; padding-top:12px; }
div[data-testid="stPlotlyChart"] { background:#fff; border:1px solid #e6e9f0; border-radius:14px; padding:6px 10px; }
</style>
"""


def page(eyebrow: str, title: str, subtitle: str, badge: str | None = None) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    b = f'<span class="rp-badge {badge}">{BADGES[badge]}</span>' if badge else ""
    st.markdown(f'<div class="rp-eyebrow">{html.escape(eyebrow)}</div><div class="rp-title">{html.escape(title)}{b}</div>'
                f'<div class="rp-sub">{subtitle}</div>', unsafe_allow_html=True)


BADGES = {"real": "Real data", "synthetic": "Synthetic data", "modeled": "Modeled estimate"}


def section(title: str, badge: str | None = None) -> None:
    b = f'<span class="rp-badge {badge}">{BADGES[badge]}</span>' if badge else ""
    st.markdown(f'<div class="rp-section">{html.escape(title)}{b}</div>', unsafe_allow_html=True)


def card(label: str, value: str, delta: str | None = None, good: bool | None = None, note: str = "") -> str:
    cls = "" if good is None else ("good" if good else "bad")
    d = f'<span class="{cls}">{html.escape(delta)}</span> ' if delta else ""
    return (f'<div class="rp-card"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div>'
            f'<div class="delta">{d}{html.escape(note)}</div></div>')


def cards(*items: str) -> None:
    st.markdown(f'<div class="rp-cards">{"".join(items)}</div>', unsafe_allow_html=True)


def callout(head: str, body: str, kind: str = "info") -> None:
    st.markdown(f'<div class="rp-callout {kind}"><div class="head">{html.escape(head)}</div>'
                f'<div class="body">{body}</div></div>', unsafe_allow_html=True)


def footer(text: str) -> None:
    st.markdown(f'<div class="rp-foot">{text}</div>', unsafe_allow_html=True)


def signed(v: float, fmt: str = "{:,.0f}", unit: str = "") -> str:
    return ("+" if v >= 0 else "−") + unit + fmt.format(abs(v))


@st.cache_data
def results(name: str) -> dict:
    return json.loads((config.RESULTS_DIR / name).read_text())


@st.cache_data
def snap(name: str) -> pd.DataFrame:
    df = pd.read_csv(snapshot.DIR / f"{name}.csv")
    return df.assign(day=pd.to_datetime(df["day"])) if "day" in df else df


@st.cache_data
def forecast_frame() -> pd.DataFrame:
    return pd.read_csv(config.RESULTS_DIR / "uci_forecast.csv", parse_dates=["day"])
