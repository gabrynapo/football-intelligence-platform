"""Plotly figures with one visual language for the Brighton dashboard."""

import plotly.graph_objects as go

BLUE = "#1475E1"
NAVY = "#102F55"
TEAL = "#17A398"
GOLD = "#E8B44C"


def finish(fig, height=310, y_title=None):
    fig.update_layout(height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=12, r=16, t=24, b=20), font=dict(family="Arial", color=NAVY),
                      legend=dict(orientation="h", y=1.16, x=0), hovermode="x unified")
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="#E8EDF4", zeroline=False, title=y_title)
    return fig


def points_chart(seasons):
    fig = go.Figure()
    colors = [BLUE, TEAL, GOLD, "#9671CB"]
    for (label, rows), color in zip(seasons.items(), colors):
        played = [r for r in rows if r["played"]]
        fig.add_trace(go.Scatter(x=[0] + [r["game"] for r in played],
                                 y=[0] + [r["cumulative_points"] for r in played],
                                 name=label, mode="lines+markers", line=dict(color=color, width=3),
                                 marker=dict(size=6), hovertemplate="%{y} punti<extra>%{fullData.name}</extra>"))
    finish(fig, y_title="Punti")
    fig.update_xaxes(title="Partite giocate", dtick=5 if any(len(v) > 20 for v in seasons.values()) else 1)
    fig.update_yaxes(rangemode="tozero")
    return fig


def goals_chart(rows):
    played = [r for r in rows if r["played"]]
    fig = go.Figure()
    for field, name, color in (("gf", "Gol fatti", BLUE), ("ga", "Gol subiti", GOLD)):
        fig.add_bar(x=[r["game"] for r in played], y=[r[field] for r in played], name=name,
                    marker_color=color, customdata=[r["opponent"] for r in played],
                    hovertemplate="%{customdata}<br>%{y} gol<extra>%{fullData.name}</extra>")
    finish(fig, y_title="Gol")
    fig.update_layout(barmode="group", bargap=.3)
    fig.update_xaxes(title="Partite giocate")
    fig.update_yaxes(dtick=1)
    return fig


def form_chart(rows):
    played = [r for r in rows if r["played"]]
    fig = go.Figure(go.Scatter(x=[r["game"] for r in played], y=[r["rolling_points"] for r in played],
                              mode="lines+markers", fill="tozeroy", line=dict(color=TEAL, width=3),
                              fillcolor="rgba(23,163,152,.10)", hovertemplate="%{y:.2f} punti/gara<extra></extra>"))
    finish(fig, 250, "Punti / gara")
    fig.update_yaxes(range=[0, 3.15])
    fig.update_xaxes(title="Partite giocate")
    return fig
