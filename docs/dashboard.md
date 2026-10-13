# Brighton dashboard

The Streamlit interface is entirely in English and runs on `127.0.0.1:8501`.
It uses local Understat CSV exports for completed seasons and a cached live
Understat snapshot, loaded through `soccerdata`, for the current season. No API
token is used by the dashboard.

Set `FOOTBALL_API_BASE_URL=http://127.0.0.1:8000` to read the same data through
the optional local FastAPI backend. Without it, Streamlit reads `UnderstatSource`
directly. Both modes follow the same data contract and cache layout. Keep the
backend on loopback because it does not provide public-user authentication.

## Interface

The sidebar selects a discovered local season or the current season. The overview
shows results, xG, xGA, xPTS, player xA, PPDA and deep completions. The standings
table exposes every field supplied by `pl-standings_YYYY-YYYY.csv`, with Brighton
highlighted. The Players tab retains every Brighton player field from
`pl-players_YYYY-YYYY.csv`, including non-penalty values, xGChain, xGBuildup and
per-90 values.

The season-comparison view charts team xG and player xA, goals versus xG, and
points versus xPTS. Team xG is taken from the standing export; it is never
replaced by a sum of player xG.

Historical exports hold season aggregates, so historical fixture-level charts and
the next-match card are deliberately unavailable. The live season includes fixtures
and shows cumulative points, goals, form, xG and xGA when Understat supplies
completed match data. Understat has no authoritative kickoff timezone in this
resource; live fixtures are displayed at day precision rather than with invented
times.

## Transfer rows and totals

The local filter retains a player when `team` contains `Brighton` as one of its
comma-separated clubs. A row such as `Arsenal,Brighton` is a combined season total,
not a Brighton-only split. It stays visible in tables and exports with
`multi_club=true`, but it is excluded from Brighton-only player totals and charts.
The UI labels xA as partial and hatches comparison bars whenever such rows exist.

## Cache and refresh behaviour

Historical CSV reads never make a network request. The current-season bundle is
stored under `data/cache/understat/` for one hour. Manual refresh observes a
60-second cooldown. A failed live request is cached for five minutes; if a previous
snapshot exists it remains visible with a stale warning. A lock in
`.state/understat/` prevents two local processes from refreshing the same season
at once. The loader uses bounded requests, timeouts and no automatic retries.

## Checks

Run:

```powershell
.venv\Scripts\python.exe scripts\check_understat.py
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The test suite uses synthetic data and never calls Understat. The live check writes
only to the ignored local cache.
