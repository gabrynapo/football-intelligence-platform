"""Brighton season dashboard. Launch: streamlit run app/streamlit_app.py."""

from datetime import datetime, timezone
from base64 import b64encode
from html import escape
from pathlib import Path
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
from football_intelligence.football_data import token_from_environment
from charts import form_chart, goals_chart, points_chart

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
.form-V {background:#dff4ec;color:#197355}.form-P {background:#fff1d6;color:#986c1d}.form-S {background:#fde6e4;color:#b14641}
div[data-testid="stTabs"] {margin-top:24px;}
button[data-baseweb="tab"] {font-size:15px;}
@media(max-width:700px){.hero{padding:24px}.hero h1{font-size:29px}.block-container{padding-top:1rem}}
</style>""", unsafe_allow_html=True)


def local_date(date):
    return date.astimezone(ROME).strftime("%d/%m/%Y · %H:%M") if date else "Data da definire"


def stamp(value):
    return local_date(datetime.fromisoformat(value)) if value else "—"


def show_issue(dataset, label):
    if dataset.error:
        st.warning(f"{label}: {dataset.error}" + (" Visualizzi l'ultima copia salvata, non aggiornata." if dataset.stale else ""))


def request_standings_refresh():
    st.session_state["refresh_standings"] = True


def card(label, value, sub):
    st.markdown(f'<div class="match-card"><div class="label">{escape(label)}</div><div class="value">{value}</div><div class="sub">{escape(sub)}</div></div>', unsafe_allow_html=True)


def display_matches(rows):
    states = {"FINISHED": "Conclusa", "SCHEDULED": "In programma", "TIMED": "In programma", "POSTPONED": "Rinviata",
              "CANCELLED": "Annullata", "IN_PLAY": "In corso", "PAUSED": "Intervallo", "SUSPENDED": "Sospesa"}
    return pd.DataFrame([{"Data (Roma)": local_date(r["date"]), "Giornata": r["matchday"], "Avversaria": r["opponent"],
                          "Campo": r["venue"], "Risultato BHA": f"{r['gf']}–{r['ga']}" if r["played"] else "—",
                          "Esito": r["result"] or "—", "Punti": r["points"], "Stato": states.get(r["status"], r["status"])} for r in rows])


with st.sidebar:
    logo_data = b64encode((ROOT / "resources" / "logo_brighton.png").read_bytes()).decode("ascii")
    st.markdown(f'<div class="brand"><img class="crest" src="data:image/png;base64,{logo_data}" alt="Logo Brighton & Hove Albion"> Brighton<small>FOOTBALL INTELLIGENCE</small></div>', unsafe_allow_html=True)
    st.caption("IL TUO OSSERVATORIO SUL CLUB")
try:
    token = token_from_environment(ROOT / ".env" if (ROOT / ".env").exists() else None)
except (OSError, StopProbe):
    st.error("Impossibile leggere la configurazione locale. Controlla FOOTBALL_DATA_TOKEN in .env.")
    st.stop()
source = DashboardSource(token)
with st.spinner("Caricamento delle stagioni…"):
    catalog = source.catalog()
show_issue(catalog, "Stagioni")
if not catalog.data:
    st.info("La dashboard richiede un token football-data.org valido. Nessun dato dimostrativo viene usato.")
    st.stop()
try:
    seasons = season_options(catalog.data)
except (KeyError, TypeError, ValueError):
    st.error("Il catalogo stagioni ricevuto non è valido.")
    st.stop()
with st.sidebar:
    season = st.selectbox("Stagione", seasons, format_func=season_label)
    st.caption("Le stagioni sono elencate nel catalogo. L'accesso dipende dal piano del tuo account.")
    refresh = st.button("↻ Aggiorna stagione", width="stretch")
    st.divider()
    st.markdown("**Un club, ogni prospettiva.**")
    st.caption("Segui risultati, punti e gol. Confronta le stagioni rispetto alle partite effettivamente giocate.")
    st.divider()
    st.caption("Dati: football-data.org\n\nRisultati in ritardo · Orari Europe/Rome")

st.markdown(f'<div class="hero"><div class="eyebrow">PREMIER LEAGUE / SEASON CENTRE</div><h1>Il Brighton, partita dopo partita.</h1><p>Risultati, forma e numeri per leggere la stagione degli Albion.</p><span class="pill">STAGIONE {season_label(season)}</span> <span class="pill">BRIGHTON & HOVE ALBION</span></div>', unsafe_allow_html=True)
with st.spinner("Caricamento dei risultati e della classifica…"):
    matches = source.matches(season, refresh)
    # If access to the season is denied, do not waste another request on its table.
    refresh_table = st.session_state.pop("refresh_standings", False)
    standings = source.standings(season, refresh or refresh_table) if matches.data else None
show_issue(matches, "Partite")
if not matches.data:
    st.info("Questa stagione non è disponibile al momento. Seleziona un'altra stagione dalla barra laterale.")
    st.stop()
if standings:
    show_issue(standings, "Classifica")
try:
    rows = match_rows(matches.data)
except (ValueError, KeyError, TypeError):
    st.error("I risultati contengono dati incoerenti. Il riepilogo è sospeso per evitare statistiche errate.")
    st.stop()
if not rows:
    st.info("Nessuna partita Brighton restituita per questa stagione.")
    st.stop()
played = [r for r in rows if r["played"]]
stats = summary(rows)
table = total_table(standings.data if standings else None)
club_row = next((r for r in table if r.get("team", {}).get("id") == BRIGHTON_ID), {})
st.caption(f"Partite aggiornate: {stamp(matches.fetched_at)} · Classifica: {stamp(standings.fetched_at) if standings else 'non disponibile'}")
invalid = sum(r["status"] == "FINISHED" and not r["played"] for r in rows)
if invalid:
    st.warning(f"{invalid} partite concluse hanno dati incompleti o incoerenti: escluse dai calcoli.")
if club_row and club_row.get("points") != stats["points"]:
    st.info("I punti calcolati dai risultati differiscono dalla classifica del provider. Gli aggiornamenti o eventuali rettifiche possono avere tempi diversi.")
metrics = st.columns(5)
for col, label, value, detail in zip(metrics,
    ["Punti conquistati", "Posizione", "Punti / partita", "Gol fatti", "Gol subiti"],
    [stats["points"] if played else "—", f"{club_row['position']}°" if club_row.get("position") else "—",
     f"{stats['ppg']:.2f}" if played else "—", stats["gf"] if played else "—", stats["ga"] if played else "—"],
    [f"{stats['played']} partite concluse", "Classifica del provider", "Media stagionale", "Totale Brighton", "Totale Brighton"]):
    col.metric(label, value, help=detail)
st.write("")
last_col, form_col, next_col = st.columns(3)
with last_col:
    if played:
        last = played[-1]
        card("Ultimo risultato", f"{last['gf']} – {last['ga']} · {escape(last['opponent'])}", f"Brighton {last['venue'].lower()} · {local_date(last['date'])}")
    else:
        card("Ultimo risultato", "Stagione da giocare", "Nessuna partita conclusa disponibile")
with form_col:
    form = "".join(f'<span class="form form-{r["result"]}">{r["result"]}</span>' for r in played[-5:])
    card("Forma · ultime 5", form or "—", "Vittoria · Pareggio · Sconfitta | da sinistra a destra")
with next_col:
    now = datetime.now(timezone.utc)
    upcoming = [r for r in rows if r["status"] in ("SCHEDULED", "TIMED") and r["date"] and r["date"] > now]
    if upcoming:
        nxt = upcoming[0]
        card("Prossima partita", escape(nxt["opponent"]), f"{nxt['venue']} · {local_date(nxt['date'])}")
    else:
        card("Prossima partita", "Nessuna gara in programma", "Nel calendario restituito per la stagione")

overview, fixtures_tab, table_tab, compare = st.tabs(["Panoramica", "Partite", "Classifica", "Confronto stagioni"])
with overview:
    if not played:
        st.info("I grafici saranno disponibili dopo le prime partite concluse.")
    else:
        left, right = st.columns([1.25, 1])
        with left, st.container(border=True):
            st.subheader("La corsa ai punti")
            st.caption("Punti cumulati, nell'ordine in cui le partite sono state giocate.")
            st.plotly_chart(points_chart({season_label(season): rows}), width="stretch", key="points")
        with right, st.container(border=True):
            st.subheader("Attacco e difesa")
            st.caption("Gol fatti e subiti in ogni partita conclusa.")
            st.plotly_chart(goals_chart(rows), width="stretch", key="goals")
        left, right = st.columns([1.25, 1])
        with left, st.container(border=True):
            st.subheader("Il momento della squadra")
            st.caption("Punti per gara nelle ultime 5 partite; a inizio stagione, nelle gare disponibili.")
            st.plotly_chart(form_chart(rows), width="stretch", key="form")
        with right, st.container(border=True):
            st.subheader("Casa e trasferta")
            split = []
            for venue in ("Casa", "Trasferta"):
                s = summary([r for r in rows if r["venue"] == venue])
                split.append({"Campo": venue, "G": s["played"], "V": s["wins"], "P": s["draws"], "S": s["losses"],
                              "Pt": s["points"], "GF": s["gf"], "GS": s["ga"], "Pt/G": round(s["ppg"], 2) if s["ppg"] is not None else None})
            st.dataframe(pd.DataFrame(split), hide_index=True, width="stretch")
            st.caption("G = giocate · V/P/S = vittorie/pareggi/sconfitte · Pt/G = punti per gara")
            a, b = st.columns(2)
            a.metric("Vittorie", f"{stats['wins']} / {stats['played']}")
            b.metric("Clean sheet", stats["clean_sheets"])

with fixtures_tab:
    st.subheader("Il calendario degli Albion")
    field, state = st.columns(2)
    venue = field.selectbox("Campo", ["Tutti", "Casa", "Trasferta"])
    phase = state.selectbox("Partite", ["Tutte", "Concluse", "Da giocare / altri stati"])
    filtered = [r for r in rows if (venue == "Tutti" or r["venue"] == venue)
                and (phase == "Tutte" or r["played"] == (phase == "Concluse"))]
    frame = display_matches(filtered)
    if frame.empty:
        st.info("Nessuna partita corrisponde ai filtri.")
    else:
        st.dataframe(frame, hide_index=True, width="stretch", height=480)
        st.download_button("Scarica le partite filtrate · CSV", frame.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"brighton-{season}-partite.csv", mime="text/csv")
    st.caption("Il punteggio è sempre espresso dal punto di vista del Brighton. I dati non disponibili restano vuoti.")

with table_tab:
    st.subheader(f"Premier League · {season_label(season)}")
    if not table:
        if standings and standings.error:
            st.warning(f"Classifica {season_label(season)}: {standings.error}")
            if standings.http_status:
                st.caption(f"Risposta del servizio: HTTP {standings.http_status}.")
        elif standings and standings.data is not None:
            st.info(f"Per il {season_label(season)}, football-data.org ha restituito una risposta senza righe nella classifica generale. I risultati delle partite possono essere comunque disponibili.")
        else:
            st.info(f"La classifica {season_label(season)} non è stata caricata. Puoi riprovare senza aggiornare i risultati delle partite.")
        st.button("Ricarica classifica", on_click=request_standings_refresh)
        st.caption("L'aggiornamento rispetta il limite richieste e un intervallo minimo di 60 secondi dall'ultima risposta salvata.")
    else:
        standings_frame = pd.DataFrame([{"Pos": r.get("position"), "Squadra": r.get("team", {}).get("name"),
                                         "G": r.get("playedGames"), "V": r.get("won"), "P": r.get("draw"), "S": r.get("lost"),
                                         "GF": r.get("goalsFor"), "GS": r.get("goalsAgainst"), "DG": r.get("goalDifference"),
                                         "Punti": r.get("points")} for r in table])
        styled = standings_frame.style.apply(lambda row: ["background-color: #e3efff; color: #123456; font-weight: bold" if "Brighton" in str(row["Squadra"]) else ""] * len(row), axis=1)
        st.dataframe(styled, hide_index=True, width="stretch", height=740)
        st.caption("Classifica restituita dal provider. Non viene ricostruita applicando criteri di spareggio arbitrari.")

with compare:
    st.subheader("Come cambia il Brighton")
    st.caption("Confronta fino a tre stagioni con quella selezionata. I dati storici vengono richiesti solo premendo il pulsante.")
    with st.form("compare_seasons"):
        requested = st.multiselect("Stagioni da confrontare", [s for s in seasons if s != season], format_func=season_label, max_selections=3)
        submitted = st.form_submit_button("Confronta le stagioni")
    if submitted:
        st.session_state["comparison"] = (season, requested)
    active_season, chosen = st.session_state.get("comparison", (season, []))
    if active_season != season:
        chosen = []
    comparisons = {season_label(season): rows}
    for other in chosen:
        with st.spinner(f"Caricamento stagione {season_label(other)}…"):
            historic = source.matches(other)
        show_issue(historic, season_label(other))
        if historic.data:
            try:
                other_rows = match_rows(historic.data)
                if any(r["played"] for r in other_rows):
                    comparisons[season_label(other)] = other_rows
                else:
                    st.info(f"{season_label(other)}: nessun risultato Brighton disponibile.")
            except (ValueError, KeyError, TypeError):
                st.warning(f"{season_label(other)}: risultati incoerenti; stagione esclusa dal confronto.")
    if chosen and len(comparisons) > 1:
        st.plotly_chart(points_chart(comparisons), width="stretch", key="comparison")
        comparison_rows = []
        for label, season_rows in comparisons.items():
            s = summary(season_rows)
            comparison_rows.append({"Stagione": label, "Giocate": s["played"], "Punti": s["points"],
                                    "Punti / gara": round(s["ppg"], 2) if s["ppg"] is not None else None,
                                    "GF": s["gf"], "GS": s["ga"]})
        st.dataframe(pd.DataFrame(comparison_rows), hide_index=True, width="stretch")
        st.caption("La stagione in corso è parziale: confronta le curve a parità di gare giocate e usa la media punti.")
    elif not chosen:
        st.info("Seleziona almeno una stagione per iniziare il confronto.")

st.divider()
st.caption("Football Intelligence Platform · Dati forniti da football-data.org · Analisi descrittiva, nessuna previsione generata.")
