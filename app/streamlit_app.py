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
from football_intelligence.analytics import BRIGHTON_ID, match_rows, season_label, season_options, summary, total_table
from football_intelligence.api import StopProbe
from football_intelligence.dashboard_data import DashboardSource
from football_intelligence.dashboard_client import ApiDashboardSource
from football_intelligence.football_data import token_from_environment
from charts import form_chart, goals_chart, points_chart
from squad_view import render_squad

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
.form {display:inline-block;padding:6px 10px;border-radius:7px;margin:0 5px 3px 0;font-size:13px;font-weight:800;}
.form-W {background:#dff4ec;color:#197355}.form-D {background:#fff1d6;color:#986c1d}.form-L {background:#fde6e4;color:#b14641}
div[data-testid="stTabs"] {margin-top:24px;}
button[data-baseweb="tab"] {font-size:15px;}
@media(max-width:700px){.hero{padding:24px}.hero h1{font-size:29px}.block-container{padding-top:1rem}}
</style>""", unsafe_allow_html=True)


def local_date(date):
    return date.astimezone(ROME).strftime("%d/%m/%Y · %H:%M") if date else "Date to be confirmed"


def stamp(value):
    return local_date(datetime.fromisoformat(value)) if value else "—"


def show_issue(dataset, label):
    if dataset.error:
        st.warning(f"{label}: {dataset.error}" + (" Showing the last saved copy; it is not up to date." if dataset.stale else ""))


def request_standings_refresh():
    st.session_state["refresh_standings"] = True


def card(label, value, sub):
    st.markdown(f'<div class="match-card"><div class="label">{escape(label)}</div><div class="value">{value}</div><div class="sub">{escape(sub)}</div></div>', unsafe_allow_html=True)


def display_matches(rows):
    states = {"FINISHED": "Finished", "SCHEDULED": "Scheduled", "TIMED": "Scheduled", "POSTPONED": "Postponed",
              "CANCELLED": "Cancelled", "IN_PLAY": "In progress", "PAUSED": "Half-time", "SUSPENDED": "Suspended"}
    return pd.DataFrame([{"Date (Rome)": local_date(r["date"]), "Matchday": r["matchday"], "Opponent": r["opponent"],
                          "Venue": r["venue"], "BHA score": f"{r['gf']}–{r['ga']}" if r["played"] else "—",
                          "Result": r["result"] or "—", "Points": r["points"], "Status": states.get(r["status"], r["status"])} for r in rows])


with st.sidebar:
    logo_data = b64encode((ROOT / "resources" / "logo_brighton.png").read_bytes()).decode("ascii")
    st.markdown(f'<div class="brand"><img class="crest" src="data:image/png;base64,{logo_data}" alt="Brighton & Hove Albion logo"> Brighton<small>FOOTBALL INTELLIGENCE</small></div>', unsafe_allow_html=True)
    st.caption("YOUR VIEW OF THE CLUB")
backend_url = os.environ.get("FOOTBALL_API_BASE_URL", "").strip()
if backend_url:
    try:
        source = ApiDashboardSource(backend_url)
    except ValueError:
        st.error("FOOTBALL_API_BASE_URL must be a valid HTTP(S) backend URL.")
        st.stop()
else:
    try:
        token = token_from_environment(ROOT / ".env" if (ROOT / ".env").exists() else None)
    except (OSError, StopProbe):
        st.error("Unable to read the local configuration. Check FOOTBALL_DATA_TOKEN in .env.")
        st.stop()
    source = DashboardSource(token)
with st.spinner("Loading seasons…"):
    catalog = source.catalog()
show_issue(catalog, "Seasons")
if not catalog.data:
    st.info("The dashboard requires a valid football-data.org token. No demo data is used.")
    st.stop()
try:
    seasons = season_options(catalog.data)
except (KeyError, TypeError, ValueError):
    st.error("The season catalogue returned by the provider is invalid.")
    st.stop()
with st.sidebar:
    season = st.selectbox("Season", seasons, format_func=season_label)
    st.caption("Seasons are listed in the catalogue. Access depends on your account plan.")
    refresh = st.button("↻ Refresh season", width="stretch")
    st.divider()
    st.markdown("**One club, every perspective.**")
    st.caption("Track results, points and goals. Compare seasons by matches played.")
    st.divider()
    st.caption("Data: football-data.org\n\nDelayed results · Times in Europe/Rome")

st.markdown(f'<div class="hero"><div class="eyebrow">PREMIER LEAGUE / SEASON CENTRE</div><h1>Brighton, match by match.</h1><p>Results, form and numbers behind the Albion season.</p><span class="pill">SEASON {season_label(season)}</span> <span class="pill">BRIGHTON & HOVE ALBION</span></div>', unsafe_allow_html=True)
with st.spinner("Loading results and standings…"):
    matches = source.matches(season, refresh)
    # If access to the season is denied, do not waste another request on its table.
    refresh_table = st.session_state.pop("refresh_standings", False)
    standings = source.standings(season, refresh or refresh_table) if matches.data else None
show_issue(matches, "Matches")
if not matches.data:
    st.info("This season is currently unavailable. Select another season in the sidebar.")
    render_squad(source)
    st.stop()
if standings:
    show_issue(standings, "Standings")
try:
    rows = match_rows(matches.data)
except (ValueError, KeyError, TypeError):
    st.error("The results contain inconsistent data. The summary is unavailable to avoid displaying incorrect statistics.")
    st.stop()
if not rows:
    st.info("No Brighton matches were returned for this season.")
    render_squad(source)
    st.stop()
played = [r for r in rows if r["played"]]
stats = summary(rows)
table = total_table(standings.data if standings else None)
club_row = next((r for r in table if r.get("team", {}).get("id") == BRIGHTON_ID), {})
st.caption(f"Matches updated: {stamp(matches.fetched_at)} · Standings: {stamp(standings.fetched_at) if standings else 'not available'}")
invalid = sum(r["status"] == "FINISHED" and not r["played"] for r in rows)
if invalid:
    st.warning(f"{invalid} finished matches have incomplete or inconsistent data and are excluded from calculations.")
if club_row and club_row.get("points") != stats["points"]:
    st.info("Points calculated from results differ from the provider's standings. Updates or adjustments may arrive at different times.")
metrics = st.columns(5)
for col, label, value, detail in zip(metrics,
    ["Points earned", "Position", "Points / match", "Goals for", "Goals against"],
    [stats["points"] if played else "—", club_row["position"] if club_row.get("position") else "—",
     f"{stats['ppg']:.2f}" if played else "—", stats["gf"] if played else "—", stats["ga"] if played else "—"],
    [f"{stats['played']} finished matches", "Provider standings", "Season average", "Brighton total", "Brighton total"]):
    col.metric(label, value, help=detail)
st.write("")
last_col, form_col, next_col = st.columns(3)
with last_col:
    if played:
        last = played[-1]
        card("Latest result", f"{last['gf']} – {last['ga']} · {escape(last['opponent'])}", f"Brighton {last['venue'].lower()} · {local_date(last['date'])}")
    else:
        card("Latest result", "Season yet to start", "No finished matches available")
with form_col:
    form = "".join(f'<span class="form form-{r["result"]}">{r["result"]}</span>' for r in played[-5:])
    card("Form · last 5", form or "—", "Win · Draw · Loss | left to right")
with next_col:
    now = datetime.now(timezone.utc)
    upcoming = [r for r in rows if r["status"] in ("SCHEDULED", "TIMED") and r["date"] and r["date"] > now]
    if upcoming:
        nxt = upcoming[0]
        card("Next match", escape(nxt["opponent"]), f"{nxt['venue']} · {local_date(nxt['date'])}")
    else:
        card("Next match", "No upcoming matches", "In the schedule returned for this season")

overview, fixtures_tab, table_tab, compare, squad_tab = st.tabs(["Overview", "Matches", "Standings", "Season comparison", "Current squad"])
with overview:
    if not played:
        st.info("Charts will be available after the first matches are completed.")
    else:
        left, right = st.columns([1.25, 1])
        with left, st.container(border=True):
            st.subheader("The race for points")
            st.caption("Cumulative points, in the order matches were played.")
            st.plotly_chart(points_chart({season_label(season): rows}), width="stretch", key="points")
        with right, st.container(border=True):
            st.subheader("Attack and defence")
            st.caption("Goals scored and conceded in each completed match.")
            st.plotly_chart(goals_chart(rows), width="stretch", key="goals")
        left, right = st.columns([1.25, 1])
        with left, st.container(border=True):
            st.subheader("Recent form")
            st.caption("Points per match over the last 5 matches, or the available matches early in the season.")
            st.plotly_chart(form_chart(rows), width="stretch", key="form")
        with right, st.container(border=True):
            st.subheader("Home and away")
            split = []
            for venue in ("Home", "Away"):
                s = summary([r for r in rows if r["venue"] == venue])
                split.append({"Venue": venue, "Pld": s["played"], "W": s["wins"], "D": s["draws"], "L": s["losses"],
                              "Pts": s["points"], "GF": s["gf"], "GA": s["ga"], "Pts/MP": round(s["ppg"], 2) if s["ppg"] is not None else None})
            st.dataframe(pd.DataFrame(split), hide_index=True, width="stretch")
            st.caption("Pld = played · W/D/L = wins/draws/losses · Pts/MP = points per match")
            a, b = st.columns(2)
            a.metric("Wins", f"{stats['wins']} / {stats['played']}")
            b.metric("Clean sheets", stats["clean_sheets"])

with fixtures_tab:
    st.subheader("Albion's fixtures")
    field, state = st.columns(2)
    venue = field.selectbox("Venue", ["All", "Home", "Away"])
    phase = state.selectbox("Matches", ["All", "Finished", "Upcoming / other statuses"])
    filtered = [r for r in rows if (venue == "All" or r["venue"] == venue)
                and (phase == "All" or r["played"] == (phase == "Finished"))]
    frame = display_matches(filtered)
    if frame.empty:
        st.info("No matches match the filters.")
    else:
        st.dataframe(frame, hide_index=True, width="stretch", height=480)
        st.download_button("Download filtered matches · CSV", frame.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"brighton-{season}-matches.csv", mime="text/csv")
    st.caption("Scores are always shown from Brighton's perspective. Unavailable data is left blank.")

with table_tab:
    st.subheader(f"Premier League · {season_label(season)}")
    if not table:
        if standings and standings.error:
            st.warning(f"Standings {season_label(season)}: {standings.error}")
            if standings.http_status:
                st.caption(f"Service response: HTTP {standings.http_status}.")
        elif standings and standings.data is not None:
            st.info(f"For {season_label(season)}, football-data.org returned no rows in the overall standings. Match results may still be available.")
        else:
            st.info(f"The {season_label(season)} standings could not be loaded. You can retry without refreshing match results.")
        st.button("Reload standings", on_click=request_standings_refresh)
        st.caption("Refresh respects the request limit and a minimum interval of 60 seconds since the last saved response.")
    else:
        standings_frame = pd.DataFrame([{"Pos": r.get("position"), "Team": r.get("team", {}).get("name"),
                                         "Pld": r.get("playedGames"), "W": r.get("won"), "D": r.get("draw"), "L": r.get("lost"),
                                         "GF": r.get("goalsFor"), "GA": r.get("goalsAgainst"), "GD": r.get("goalDifference"),
                                         "Points": r.get("points")} for r in table])
        styled = standings_frame.style.apply(lambda row: ["background-color: #e3efff; color: #123456; font-weight: bold" if "Brighton" in str(row["Team"]) else ""] * len(row), axis=1)
        st.dataframe(styled, hide_index=True, width="stretch", height=740)
        st.caption("Standings as returned by the provider, without applying custom tie-break rules.")

with compare:
    st.subheader("Brighton through the seasons")
    st.caption("Compare up to three seasons with the selected season. Historical data is requested only when you press the button.")
    with st.form("compare_seasons"):
        requested = st.multiselect("Seasons to compare", [s for s in seasons if s != season], format_func=season_label, max_selections=3)
        submitted = st.form_submit_button("Compare seasons")
    if submitted:
        st.session_state["comparison"] = (season, requested)
    active_season, chosen = st.session_state.get("comparison", (season, []))
    if active_season != season:
        chosen = []
    comparisons = {season_label(season): rows}
    for other in chosen:
        with st.spinner(f"Loading season {season_label(other)}…"):
            historic = source.matches(other)
        show_issue(historic, season_label(other))
        if historic.data:
            try:
                other_rows = match_rows(historic.data)
                if any(r["played"] for r in other_rows):
                    comparisons[season_label(other)] = other_rows
                else:
                    st.info(f"{season_label(other)}: no Brighton results available.")
            except (ValueError, KeyError, TypeError):
                st.warning(f"{season_label(other)}: inconsistent results; season excluded from comparison.")
    if chosen and len(comparisons) > 1:
        st.plotly_chart(points_chart(comparisons), width="stretch", key="comparison")
        comparison_rows = []
        for label, season_rows in comparisons.items():
            s = summary(season_rows)
            comparison_rows.append({"Season": label, "Played": s["played"], "Points": s["points"],
                                    "Points / match": round(s["ppg"], 2) if s["ppg"] is not None else None,
                                    "GF": s["gf"], "GA": s["ga"]})
        st.dataframe(pd.DataFrame(comparison_rows), hide_index=True, width="stretch")
        st.caption("The current season is incomplete: compare curves at the same number of matches played and use average points.")
    elif not chosen:
        st.info("Select at least one season to start comparing.")

with squad_tab:
    render_squad(source)

st.divider()
st.caption("Football Intelligence Platform · Data provided by football-data.org · Descriptive analysis; no predictions generated.")
