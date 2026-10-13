"""Understat Brighton player analysis for the selected season."""

import pandas as pd
import plotly.express as px
import streamlit as st

from football_intelligence.analytics import season_label
from football_intelligence.understat_data import player_totals
from charts import finish
from metric_labels import PLAYER_LABELS


def render_players(data, season):
    st.subheader(f"Brighton players · {season_label(season)}")
    players = data.get("players", [])
    if not players:
        st.info("No Brighton player statistics are available for this season.")
        return
    frame = pd.DataFrame(players)
    totals = player_totals(players)
    metrics = st.columns(4)
    for col, label, value in zip(metrics, ["Players", "Recorded goals", "Recorded assists", "xA" if totals["xA_complete"] else "xA (partial)"],
                               [len(players), totals["goals"], totals["assists"], totals["xA"]]):
        col.metric(label, "—" if value is None else f"{value:.2f}" if label.startswith("xA") else f"{value:g}")
    if totals["excluded_multi_club"]:
        st.warning(f"{totals['excluded_multi_club']} player row(s) combine Brighton with another club. Their statistics are retained and labelled, but excluded from club totals and charts. Brighton-only xA is incomplete for this season.")
    st.caption("Season participants, not the current squad. All supplied CSV fields are available in the table and export. Missing values remain blank.")
    search_col, minute_col = st.columns(2)
    search = search_col.text_input("Find a player", key=f"player_search_{season}")
    minutes = minute_col.number_input("Minimum minutes", min_value=0, max_value=10000, value=0, step=90, key=f"player_minutes_{season}")
    include_transfers = st.checkbox("Include rows covering multiple clubs", value=True, key=f"player_transfers_{season}")
    filtered = frame[frame["player"].str.contains(search, case=False, regex=False, na=False)]
    if minutes:
        filtered = filtered[filtered["min"].ge(minutes)]
    if not include_transfers:
        filtered = filtered[~filtered["multi_club"]]
    if filtered.empty:
        st.info("No players match the filters.")
        return
    chart_frame = filtered[~filtered["multi_club"]]
    left, right = st.columns(2)
    for col, field, title, color in ((left, "xG", "Expected goals leaders", "#1475E1"),
                                     (right, "xA", "Expected assists leaders", "#17A398")):
        if chart_frame[field].notna().any():
            leaders = chart_frame.dropna(subset=[field]).nlargest(10, field)
            fig = px.bar(leaders, x="player", y=field, labels={"player": "Player"}, color_discrete_sequence=[color])
            col.subheader(title)
            col.plotly_chart(finish(fig, 320, field), width="stretch", key=f"player_{field}")
    if not chart_frame.empty:
        scatter = chart_frame.dropna(subset=["xG", "goals", "min"])
        if not scatter.empty:
            st.plotly_chart(finish(px.scatter(scatter, x="xG", y="goals", size="min", hover_name="player",
                                              labels={"goals": "Goals", "min": "Minutes"},
                                              color_discrete_sequence=["#135b9b"]), 340, "Goals"),
                            width="stretch", key="player_finishing")
    st.caption("Player charts follow the filters and use Brighton-only rows. xG and xA are expected goals and expected assists; per-90 values are rates, not totals.")
    visible = filtered.rename(columns=PLAYER_LABELS)
    st.dataframe(visible, hide_index=True, width="stretch",
                 column_config={label: st.column_config.NumberColumn(format="%.2f") for field, label in PLAYER_LABELS.items()
                                if field.startswith("x") or field.startswith("NPx")})
    st.download_button("Download filtered players · CSV", visible.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"brighton-{season}-players.csv", mime="text/csv")
    indices = filtered.index.tolist()
    selected = st.selectbox("Player profile", indices, format_func=lambda i: frame.loc[i, "player"], key=f"player_profile_{season}")
    player = frame.loc[selected]
    with st.container(border=True):
        st.subheader(player["player"])
        st.caption(f"{player['team']} · {season_label(season)}")
        if player["multi_club"]:
            st.warning("This row contains combined statistics for all listed clubs. A Brighton-only split is not available in this file.")
        fields = [field for field in frame.columns if field not in ("player", "team", "multi_club")]
        st.dataframe(pd.DataFrame({"Metric": [PLAYER_LABELS.get(f, f) for f in fields],
                                  "Value": ["—" if pd.isna(player[f]) else f"{player[f]:.2f}" if isinstance(player[f], float)
                                            else str(player[f]) for f in fields]}), hide_index=True, width="stretch")
    with st.expander("Metric guide"):
        st.markdown("**xG / xA:** expected goals and expected assists. **NPxG / NPG:** expected goals and goals excluding penalties. "
                    "**xGChain:** xG of possessions a player participates in. **xGBuildup:** contribution earlier in those possessions, excluding the final shot and key pass. "
                    "**/ 90:** rate per 90 minutes. Chain and buildup contributions overlap between teammates and should not be summed as team xG.")
