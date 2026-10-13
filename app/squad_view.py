"""Current roster view, independent of the selected competition season."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st

from football_intelligence.squad import squad_rows


def render_squad(source):
    st.subheader("Brighton's current squad")
    st.info("Current squad returned by football-data.org: this is not the historical squad for the season selected in the sidebar.")
    refresh = st.button("Refresh squad", key="refresh_squad")
    with st.spinner("Loading squad…"):
        dataset = source.squad(refresh=refresh)
    if dataset.error:
        st.warning("Squad: " + dataset.error + (" Showing the last saved copy; it is not up to date." if dataset.stale else ""))
    if dataset.data is None:
        return
    today = datetime.now(ZoneInfo("Europe/Rome")).date()
    try:
        rows = squad_rows(dataset.data, as_of=today)
    except (ValueError, TypeError, AttributeError):
        st.error("The squad data is invalid. Unable to display players.")
        return
    st.caption(f"Source: football-data.org · Retrieved (UTC): {dataset.fetched_at or 'not available'} · Cache: 24 hours; manual refresh at most once every 60 seconds.")
    if not rows:
        st.info("The provider returned an empty squad for Brighton.")
        return
    frame = pd.DataFrame([{"ID": r["id"], "Player": r["name"], "Role": r["role"],
                           "Provider position": r["position"], "Nationality": r["nationality"],
                           "Date of birth": r["birth_date"], "Age": r["age"]} for r in rows])
    frame["Age"] = frame["Age"].astype("Int64")
    ages = [r["age"] for r in rows if r["age"] is not None]
    countries = {r["nationality"] for r in rows if r["nationality"] != "Not available"}
    a, b, c = st.columns(3)
    a.metric("Squad size", len(rows))
    b.metric("Average age", f"{sum(ages) / len(ages):.1f}" if ages else "—")
    c.metric("Nationalities", len(countries))
    st.caption(f"Age as of {today:%d/%m/%Y}, available for {len(ages)}/{len(rows)} players. Missing data is left blank.")
    left, right = st.columns(2)
    with left:
        roles = frame.groupby("Role").size().reset_index(name="Players")
        chart = px.bar(roles, x="Role", y="Players", title="Squad by role", color_discrete_sequence=["#135b9b"])
        chart.update_yaxes(dtick=1)
        st.plotly_chart(chart, width="stretch", key="squad_roles")
    with right:
        if ages:
            chart = px.histogram(x=ages, title="Age distribution", labels={"x": "Age"}, color_discrete_sequence=["#399cc7"])
            chart.update_traces(xbins=dict(size=1))
            chart.update_yaxes(title="Players", dtick=1)
            st.plotly_chart(chart, width="stretch", key="squad_ages")
        else:
            st.info("Birth dates are unavailable for the age chart.")
    st.caption("Charts describe the whole squad; the filters below apply to the table and player profiles.")
    left, right = st.columns(2)
    role = left.selectbox("Role", ["All", *sorted(frame["Role"].unique())], key="squad_role")
    country = right.selectbox("Nationality", ["All", *sorted(frame["Nationality"].unique())], key="squad_country")
    filtered = frame
    if role != "All":
        filtered = filtered[filtered["Role"] == role]
    if country != "All":
        filtered = filtered[filtered["Nationality"] == country]
    if filtered.empty:
        st.info("No players match the filters.")
        return
    st.dataframe(filtered.drop(columns="ID"), hide_index=True, width="stretch",
                 column_config={"Age": st.column_config.NumberColumn(format="%d"),
                                "Date of birth": st.column_config.DateColumn(format="DD/MM/YYYY")})
    st.download_button("Download filtered squad · CSV", filtered.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"brighton-current-squad-{today}.csv", mime="text/csv")
    players = {r["id"]: r for r in rows}
    selected = st.selectbox("Player profile", filtered["ID"].tolist(),
                            format_func=lambda pid: players[pid]["name"], key="squad_player")
    player = players[selected]
    with st.container(border=True):
        st.subheader(player["name"])
        st.text(f"{player['role']} · {player['nationality']}")
        birthday = player["birth_date"].strftime("%d/%m/%Y") if player["birth_date"] else "Not available"
        st.text(f"Date of birth: {birthday} · Age: {player['age'] if player['age'] is not None else 'Not available'}")
        st.caption(f"ID football-data.org: {selected}")
    st.caption("This endpoint provides squad and player profile data. Individual appearances, minutes, goals and assists are not included in this view.")
