"""Season overview, fixtures and comparisons using the same Understat dataset."""

from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from football_intelligence.analytics import match_rows, season_label
from charts import finish, form_chart, goals_chart, points_chart, BLUE, TEAL, GOLD
from metric_labels import TEAM_LABELS
from squad_view import render_players


def fmt(value, decimals=0):
    return "—" if value is None or pd.isna(value) else f"{value:,.{decimals}f}"


def paired_chart(categories, actual, expected, names=("Actual", "Expected")):
    fig = go.Figure()
    fig.add_bar(x=categories, y=actual, name=names[0], marker_color=BLUE)
    fig.add_bar(x=categories, y=expected, name=names[1], marker_color=TEAL)
    return finish(fig)


def render_comparison(source):
    result = source.comparison()
    if result.error:
        st.warning(result.error)
    if not result.data or not result.data.get("rows"):
        st.info("No season comparisons are available.")
        return
    rows = result.data["rows"]
    seasons = [row["season"] for row in rows]
    chosen = st.multiselect("Seasons to compare", seasons, default=seasons, format_func=season_label)
    rows = [r for r in rows if r["season"] in chosen]
    for note in result.data.get("notes", []):
        st.caption(note)
    if not rows:
        st.info("Select at least one season to compare.")
        return
    labels = [season_label(r["season"]) for r in rows]
    fig = go.Figure()
    fig.add_bar(x=labels, y=[r.get("xG") for r in rows], name="Team xG", marker_color=BLUE)
    fig.add_bar(x=labels, y=[r.get("xA") for r in rows], name="Player xA (hatched = partial)", marker_color=TEAL,
                marker_pattern_shape=["" if r["xA_complete"] else "/" for r in rows],
                customdata=["Complete player rows" if r["xA_complete"] else "Partial: multi-club or missing values excluded" for r in rows],
                hovertemplate="%{x}<br>xA: %{y:.2f}<br>%{customdata}<extra></extra>")
    st.plotly_chart(finish(fig, 360, "Season total"), width="stretch", key="season_xg_xa")
    st.caption("Team xG comes from standings. xA sums Brighton-only player rows; hatched bars are partial and exclude combined transfer rows. Current-season totals cover only matches played so far.")
    left, right = st.columns(2)
    left.plotly_chart(paired_chart(labels, [r.get("goals") for r in rows], [r.get("xG") for r in rows], ("Goals", "xG")),
                      width="stretch", key="season_goals_xg")
    right.plotly_chart(paired_chart(labels, [r.get("points") for r in rows], [r.get("xPTS") for r in rows], ("Points", "Expected points")),
                       width="stretch", key="season_points_xpts")
    comparison = pd.DataFrame(rows).rename(columns={**TEAM_LABELS, "season": "Season", "xA_complete": "xA complete",
                                                   "excluded_multi_club": "Multi-club rows excluded", "source": "Source", "stale": "Stale snapshot"})
    comparison["Season"] = comparison["Season"].map(season_label)
    if "Played" in comparison:
        comparison["xG / match"] = comparison["xG"] / comparison["Played"].replace(0, float("nan"))
        comparison["xA / match"] = comparison["xA"] / comparison["Played"].replace(0, float("nan"))
    st.dataframe(comparison, hide_index=True, width="stretch")
    st.download_button("Download season comparison · CSV", comparison.to_csv(index=False).encode("utf-8-sig"),
                       file_name="brighton-season-comparison.csv", mime="text/csv")


def render_dashboard(source, season, dataset):
    data = dataset.data or {"players": [], "standings": [], "matches": [], "totals": {}, "notes": []}
    team, totals = data.get("team") or {}, data.get("totals", {})
    if dataset.error:
        st.warning(dataset.error + (" Showing the last saved snapshot." if dataset.stale else ""))
    for note in data.get("notes", []):
        st.caption(note)
    if data.get("source"):
        stamp = "CSV file modified" if data["source"] == "Understat CSV" else "Snapshot retrieved"
        st.caption(f"{data['source']} · {stamp} (UTC): {dataset.fetched_at or 'not available'}")
    metrics = st.columns(5)
    played = team.get("matches")
    for col, label, value in zip(metrics, ["Points earned", "Position", "Points / match", "Goals for", "Goals against"],
                               [fmt(team.get("points")), fmt(team.get("number")),
                                fmt(team.get("points") / played, 2) if played and team.get("points") is not None else "—",
                                fmt(team.get("goals")), fmt(team.get("ga"))]):
        col.metric(label, value)
    metrics = st.columns(4)
    for col, label, value in zip(metrics, ["Expected goals · xG", "Expected goals against · xGA", "Expected points", "xA" if totals.get("xA_complete") else "xA (partial)"],
                               [team.get("xG"), team.get("xGA"), team.get("xPTS"), totals.get("xA")]):
        col.metric(label, fmt(value, 2))
    rows = []
    if data.get("match_details_available"):
        try:
            rows = match_rows(data, team_id=data["brighton_team_id"])
        except (ValueError, KeyError, TypeError):
            st.warning("Inconsistent match data: match charts are unavailable.")
    completed = [row for row in rows if row["played"]]
    overview, matches_tab, standings_tab, compare, players_tab = st.tabs(["Overview", "Matches", "Standings", "Season comparison", "Players"])
    with overview:
        st.subheader("The season at a glance")
        st.caption(f"{fmt(played)} matches played · {fmt(team.get('wins'))} wins · {fmt(team.get('draws'))} draws · {fmt(team.get('loses'))} defeats")
        left, right = st.columns(2)
        with left, st.container(border=True):
            st.subheader("Goals and expected goals")
            st.plotly_chart(paired_chart(["Scored", "Conceded"], [team.get("goals"), team.get("ga")],
                                         [team.get("xG"), team.get("xGA")], ("Goals", "Expected goals")), width="stretch", key="overview_xg")
        with right, st.container(border=True):
            st.subheader("Points and expected points")
            st.plotly_chart(paired_chart([season_label(season)], [team.get("points")], [team.get("xPTS")],
                                         ("Points", "Expected points")), width="stretch", key="overview_xpts")
        if completed:
            last = completed[-1]
            upcoming = [r for r in rows if not r["played"] and r["status"] == "SCHEDULED"]
            a, b, c = st.columns(3)
            a.metric("Latest result", f"{last['gf']}–{last['ga']}", help=last["opponent"])
            b.metric("Last 5", " ".join(r["result"] for r in completed[-5:]))
            c.metric("Next opponent", upcoming[0]["opponent"] if upcoming else "—")
            left, right = st.columns(2)
            left.plotly_chart(points_chart({season_label(season): rows}), width="stretch", key="points")
            right.plotly_chart(goals_chart(rows), width="stretch", key="goals")
            left.plotly_chart(form_chart(rows), width="stretch", key="form")
            match_lookup = {m["id"]: m for m in data["matches"]}
            xg, xga, points = [], [], []
            total_for = total_against = 0.0
            complete_expected = True
            for row in completed:
                expected = match_lookup[row["id"]].get("expected_goals", {})
                home = row["venue"] == "Home"
                own, against = expected.get("home" if home else "away"), expected.get("away" if home else "home")
                if own is None or against is None:
                    complete_expected = False
                    break
                total_for += own
                total_against += against
                xg.append(total_for)
                xga.append(total_against)
                points.append(row["game"])
            if complete_expected:
                fig = go.Figure()
                fig.add_scatter(x=points, y=xg, name="Cumulative xG", mode="lines+markers", line_color=BLUE)
                fig.add_scatter(x=points, y=xga, name="Cumulative xGA", mode="lines+markers", line_color=GOLD)
                right.plotly_chart(finish(fig, 300, "Expected goals"), width="stretch", key="match_xg")
        elif not data.get("match_details_available"):
            st.info("The historical CSVs contain season totals, not individual matches. Match-by-match charts are available for the live season when Understat returns results.")
        st.subheader("All team statistics")
        if team:
            st.dataframe(pd.DataFrame([team]).rename(columns=TEAM_LABELS), hide_index=True, width="stretch")
        with st.expander("Advanced team metrics"):
            st.markdown("**NPxG / NPxGA:** expected goals for/against excluding penalties. **NPxGD:** their difference. "
                        "**PPDA:** opposition passes per defensive action; lower values indicate more intense pressing. "
                        "**PPDA allowed:** the opposing teams' pressing measure. **Deep completions:** passes completed close to goal. "
                        "**xPTS:** expected points from the chance-quality model. Team xG is kept separate from the sum of player xG in the supplied files.")
    with matches_tab:
        st.subheader("Albion's fixtures")
        if not rows:
            st.info("No match-level data is available for this season. Its season totals and player statistics remain available in the other tabs.")
        else:
            a, b = st.columns(2)
            venue = a.selectbox("Venue", ["All", "Home", "Away"])
            phase = b.selectbox("Matches", ["All", "Finished", "Upcoming"])
            filtered = [r for r in rows if (venue == "All" or venue == r["venue"])
                        and (phase == "All" or r["played"] == (phase == "Finished"))]
            frame = pd.DataFrame([{"Date": r["date"].strftime("%d/%m/%Y") if r["date"] else None,
                                   "Opponent": r["opponent"], "Venue": r["venue"],
                                   "BHA score": f"{r['gf']}–{r['ga']}" if r["played"] else None,
                                   "Result": r["result"], "Points": r["points"],
                                   "Status": "Finished" if r["played"] else "Scheduled"} for r in filtered])
            st.dataframe(frame, hide_index=True, width="stretch")
            st.download_button("Download filtered matches · CSV", frame.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"brighton-{season}-matches.csv", mime="text/csv")
    with standings_tab:
        st.subheader(f"Premier League · {season_label(season)}")
        table = data.get("standings", [])
        if not table:
            st.info("No standings are available for this season.")
        else:
            frame = pd.DataFrame(table).rename(columns=TEAM_LABELS)
            styled = frame.style.apply(lambda row: ["background-color: #e3efff; color: #123456; font-weight: bold"
                                                     if "Brighton" in str(row["Team"]) else ""] * len(row), axis=1)
            st.dataframe(styled, hide_index=True, width="stretch", height=740)
            st.download_button("Download standings · CSV", frame.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"premier-league-{season}-standings.csv", mime="text/csv")
    with compare:
        st.subheader("Brighton through the seasons")
        render_comparison(source)
    with players_tab:
        render_players(data, season)
