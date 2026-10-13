# Football Intelligence Platform

A Brighton-focused Premier League analytics portfolio built with Python, Streamlit
and FastAPI. The dashboard uses **Understat**, through local historical CSV exports
and `soccerdata` for the current season. The entire web interface is in English.

## Run the dashboard

Python 3.11+ is required. From the repository root:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m streamlit run app/streamlit_app.py
```

Open **http://127.0.0.1:8501**. No API token is required for Understat.
On Linux/macOS, use `.venv/bin/python` instead.

Historical input files belong in `data/`, with names such as
`pl-players_2021-2022.csv` and `pl-standings_2021-2022.csv`.
The supplied exports are semicolon-separated. The season comes from the filename.
Only player rows whose comma-separated club list contains Brighton are retained;
league standings retain all teams. Available local files populate the season selector.

**2026/27 is fetched live from Understat.** The current season is determined using
a July boundary in Europe/Rome. Historical reads never call a provider. If the live
source fails, historical seasons remain usable; an older live snapshot is shown
with a stale-data warning when one is available.

## Dashboard

- **Overview:** points, position, goals, xG, xGA, xPTS, xA and all team metrics,
  including non-penalty xG, PPDA and deep completions.
- **Matches:** current-season fixtures, results and filters. Completed live matches
  also power cumulative points, form and cumulative xG/xGA charts.
- **Standings:** every team and every advanced field in the supplied standings CSVs,
  with Brighton highlighted.
- **Season comparison:** xG and xA totals, goals versus xG, points versus expected
  points, per-match averages and CSV export.
- **Players:** Brighton season participants, appearances, minutes, goals, assists,
  non-penalty measures, xGChain, xGBuildup, all supplied per-90 columns, filters,
  profiles and CSV export. Live data also includes position, shots, key passes and cards.

Historical CSVs contain season aggregates, not individual fixtures. They cannot
support historical match-by-match charts. Those views show an availability message
while all other season information remains accessible.

Some player rows combine clubs, such as `Arsenal,Brighton`. These rows remain visible
and flagged, but are excluded from Brighton-only player totals and charts. Affected
xA bars are hatched and labelled **partial**. Exact Brighton-only xA cannot be
reconstructed from these files alone. Team xG comes directly from the standings;
player xG is not substituted for it. Per-90 rates and overlapping xGChain/xGBuildup
contributions are never summed as team totals.

## Verify and extract

```powershell
.venv/Scripts/python.exe scripts/check_understat.py
.venv/Scripts/python.exe scripts/extract_brighton.py
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

The first command verifies and caches the current season. The second creates
`data/processed/brighton-players_YYYY-YYYY.csv` for each local season, retaining
every source column and adding `multi_club`. Original files are not edited.

Verified on **13 October 2026**:

| Season | Brighton player rows | Rows combining clubs |
| --- | ---: | ---: |
| 2021/22 | 26 | 1 |
| 2022/23 | 29 | 1 |
| 2023/24 | 30 | 0 |
| 2024/25 | 32 | 2 |
| 2025/26 | 28 | 0 |
| 2026/27, live | 23 | 0 |

The live response also supplied 20 teams and 38 Brighton fixtures. These are
observations, not hard-coded counts. Raw data, caches and processed exports are
ignored by Git; CI uses synthetic fixtures and does not call Understat.

## Optional FastAPI backend

Start the backend in one terminal:

```powershell
.venv/Scripts/python.exe -m uvicorn --app-dir src football_intelligence.web_api:app --host 127.0.0.1 --port 8000
```

Then start Streamlit in another:

```powershell
$env:FOOTBALL_API_BASE_URL = 'http://127.0.0.1:8000'
.venv/Scripts/python.exe -m streamlit run app/streamlit_app.py
```

API documentation: **http://127.0.0.1:8000/docs**. Restart a backend that was running
before this provider migration.

| Endpoint | Content |
| --- | --- |
| `GET /health` | Process health; no network request |
| `GET /api/v1/seasons` | Local catalogue and current season |
| `GET /api/v1/seasons/{season}/brighton/summary` | Season bundle, team metrics and player totals |
| `GET /api/v1/seasons/{season}/brighton/players` | Filtered Brighton participants |
| `GET /api/v1/seasons/{season}/standings` | All teams and advanced statistics |
| `GET /api/v1/seasons/{season}/matches` | Fixtures when match-level data exists |
| `GET /api/v1/brighton/comparison` | Local seasons plus the saved current snapshot |
| `GET /api/v1/brighton/squad` | Compatibility alias for current-season participants |

Season routes accept `?refresh=true`. Responses retain the `data`, `fetched_at`,
`error`, `stale`, `error_code`, `http_status` envelope. The Understat payloads
replace the former provider-specific shapes. Keep this unauthenticated local
backend bound to `127.0.0.1`.

The live bundle has a **one-hour cache**, a **60-second refresh cooldown** and a
**five-minute failure cache**, shared across Streamlit and FastAPI. One season
resource supplies players, fixtures and team histories; soccerdata also initializes
its HTTP session. Requests have timeouts, no automatic retries and a cross-process
lock. Comparisons use local files and saved snapshots without extra live calls.

## Repository

```text
app/
  streamlit_app.py        # Branding, sidebar and source selection
  understat_view.py       # Overview, fixtures, standings and comparisons
  squad_view.py           # Players, charts, filters and profiles
  metric_labels.py        # English field names
  charts.py               # Shared Plotly styling and match charts
src/football_intelligence/
  understat_data.py       # CSV validation, attribution, caching and season adapter
  understat_live.py       # Isolated soccerdata adapter and live normalization
  web_api.py              # FastAPI routes
  dashboard_client.py     # Optional HTTP client for Streamlit
  analytics.py            # Pure match calculations
scripts/
  check_understat.py      # Live coverage check
  extract_brighton.py     # Local CSV extraction
tests/                   # Offline data, cache, API and Streamlit tests
docs/                    # Architecture and data semantics
```

PostgreSQL, dbt, scheduled ingestion, predictive models and Monte Carlo simulations
remain future milestones. Season-end aggregates must not be used as features for
earlier matches without point-in-time evidence.

See [data details](docs/player-data.md), [dashboard behaviour](docs/dashboard.md),
[architecture](docs/architecture.md), and the
[soccerdata Understat documentation](https://soccerdata.readthedocs.io/en/latest/reference/understat.html).
