"""Brighton season dashboard. Launch: streamlit run app/streamlit_app.py."""

from datetime import datetime, timezone
from base64 import b64encode
from html import escape
from pathlib import Path
import os
import sys
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "app"))
from football_intelligence.analytics import season_label, season_options
from football_intelligence.understat_data import UnderstatSource
from football_intelligence.dashboard_client import ApiDashboardSource
from understat_view import render_dashboard

ROME = ZoneInfo("Europe/Rome")
st.set_page_config(page_title="Brighton | Football Intelligence", page_icon="⚽", layout="wide")
st.markdown("""<style>
.block-container {max-width:1480px; padding-top:2rem; padding-bottom:3rem;}
h1,h2,h3 {letter-spacing:-.035em;}
[data-testid="stSidebar"] {border-right:1px solid #e4eaf3;}
[data-testid="stMetric"] {background:white; border:1px solid #e6ecf5; border-radius:14px; padding:18px 20px;}
[data-testid="stMetricValue"] {font-weight:750; color:#123456;}
.brand {font-weight:800;font-size:22px;line-height:1.2;margin:8px 0 30px;}
.brand small {display:block;font-size:10px;letter-spacing:2px;color:#7c8ba1;margin-top:10px;}
.crest {display:inline-block;width:56px;height:56px;object-fit:contain;vertical-align:middle;margin-right:10px;}
.hero {background:linear-gradient(115deg,#102c51,#135b9b);border-radius:20px;padding:32px 38px;color:white;margin:5px 0 24px;position:relative;overflow:hidden;}
.hero:after {content:'';position:absolute;right:-40px;top:-120px;width:430px;height:430px;border:1px solid #ffffff22;border-radius:50%;box-shadow:0 0 0 55px #ffffff05,0 0 0 110px #ffffff04;pointer-events:none;}
.hero h1 {color:white;font-size:40px;margin:10px 0 4px;font-weight:800;}
.hero p {color:#c6d9ed;margin:0;font-size:16px;}
.eyebrow {font-size:11px;letter-spacing:2px;font-weight:700;color:#9dc8f6;}
.pill {display:inline-block;background:#ffffff18;border:1px solid #ffffff26;border-radius:30px;padding:5px 12px;margin-top:18px;font-size:12px;}
.match-card {background:white;border:1px solid #e6ecf5;border-radius:14px;padding:20px;min-height:138px;}
.match-card .label {font-size:10px;text-transform:uppercase;letter-spacing:1.4px;color:#6c7e97;font-weight:700;margin-bottom:12px;}
.match-card .value {font-size:19px;font-weight:750;color:#142f50;line-height:1.35;}
.match-card .sub {font-size:12px;color:#6c7e97;margin-top:8px;}
.form-card {background:white;border:1px solid #e6ecf5;border-radius:14px;padding:18px 20px;min-height:92px;box-sizing:border-box;}
.form-card .label {font-size:14px;color:#6c7e97;font-weight:600;margin-bottom:10px;}
.form-sequence {display:flex;gap:8px;align-items:center;min-height:34px;}
.form-badge {display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:9px;font-size:14px;font-weight:800;}
.form-badge-W {background:#dff4ec;color:#197355}.form-badge-D {background:#fff1d6;color:#986c1d}.form-badge-L {background:#fde6e4;color:#b14641}
.form-card .sub {font-size:12px;color:#6c7e97;margin-top:8px;}
div[data-testid="stTabs"] {margin-top:24px;}
button[data-baseweb="tab"] {font-size:15px;}
@media(max-width:700px){.hero{padding:24px}.hero h1{font-size:29px}.block-container{padding-top:1rem}}
</style>""", unsafe_allow_html=True)


with st.sidebar:
    logo_data = b64encode((ROOT / "resources" / "logo_brighton.png").read_bytes()).decode("ascii")
    st.markdown(f'<div class="brand"><img class="crest" src="data:image/png;base64,{logo_data}" alt="Brighton & Hove Albion logo"> Brighton<small>FOOTBALL INTELLIGENCE</small></div>', unsafe_allow_html=True)
    st.caption("YOUR VIEW OF THE CLUB")

backend_url = os.environ.get("FOOTBALL_API_BASE_URL", "").strip()
try:
    source = ApiDashboardSource(backend_url) if backend_url else UnderstatSource()
except ValueError:
    st.error("FOOTBALL_API_BASE_URL must be a valid HTTP(S) backend URL.")
    st.stop()
catalog = source.catalog()
if not catalog.data:
    st.error(catalog.error or "The season catalogue is unavailable.")
    st.stop()
try:
    seasons = season_options(catalog.data)
except (KeyError, TypeError, ValueError):
    st.error("The season catalogue is invalid.")
    st.stop()

with st.sidebar:
    season = st.selectbox("Season", seasons, format_func=season_label)
    st.caption("Historical seasons: local CSVs. Current season: Understat.")
    refresh = st.button("Refresh season", width="stretch")
    st.divider()
    st.markdown("**One club, every perspective.**")
    st.caption("Results, expected goals and the players behind the numbers.")
    st.divider()
    st.caption("Data: Understat ? via soccerdata and local exports.\n\nNo API token required.")

st.markdown(f'<div class="hero"><div class="eyebrow">PREMIER LEAGUE / SEASON CENTRE</div><h1>Brighton, beyond the score.</h1><p>Results, expected goals and numbers behind the Albion season.</p><span class="pill">SEASON {season_label(season)}</span> <span class="pill">BRIGHTON & HOVE ALBION</span></div>', unsafe_allow_html=True)
with st.spinner("Loading season data?"):
    dataset = source.season(season, refresh=refresh)
render_dashboard(source, season, dataset)
st.divider()
st.caption("Football Intelligence Platform ? Understat ? Descriptive analysis; no predictions generated.")
