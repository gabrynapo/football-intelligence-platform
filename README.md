# Football Intelligence Platform

An end-to-end portfolio project in Data Engineering, Football Analytics and Machine Learning:
Premier League **2026/27**, with a dashboard initially focused on **Brighton**.

**Current stage: a Streamlit dashboard using real data.** Implemented components include
API discovery probes, the Brighton frontend, a client with persistent caching,
and offline and UI tests. The entire web interface is in English, including charts,
error messages and CSV exports. PostgreSQL, a scheduled pipeline, dbt and predictive
models are planned for later stages.

## Run the dashboard

Set the football-data.org token in the `FOOTBALL_DATA_TOKEN` environment variable
or in the local `.env` file, which is ignored by Git. From the repository in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dashboard]"
.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py
```

Open **http://127.0.0.1:8501**. If the virtual environment is already set up, only
the last command is needed. On Linux/macOS, use `.venv/bin/python` instead of
`.venv\Scripts\python.exe`.

- Season selection and metrics: points, position, average points, goals for/against.
- Interactive charts: cumulative points, goals per match and form over the last 5 matches.
- Home/away performance, latest result and next match.
- Filterable fixtures with CSV export and standings with Brighton highlighted.
- Comparison of up to four seasons at the same number of matches played.
- Brighton's current squad from football-data.org: role/nationality filters,
  player profiles, ages, squad composition charts and CSV export.

The squad is the current roster returned by `/teams/397`, regardless of the selected
season: it does not represent historical squads. It does not include individual
statistics such as minutes, goals or assists. Verified on 13 October 2026:
HTTP 200, 30 players.

The local cache lasts one hour for results/standings and 24 hours for the catalogue
and squad. Filtering tables and switching tabs do not trigger new calls for cached
resources within these intervals. Manual refresh has a minimum interval of 60 seconds.
Requests are spaced at least 6.1 seconds apart and share the request ledger with
the probe. No scheduled jobs or paid calls are enabled.
[Dashboard behaviour and limitations](docs/dashboard.md).

The API-Football Free plan advertises 100 requests/day but restricts season access.
**Authenticated check on 13 October 2026: access to 2026/27 was denied on the Free
plan.** The key works and the account is active; `/leagues?id=39&season=2026`
returns a plan restriction and suggests seasons from 2022 to 2024.
Those seasons have not yet been tested. **football-data.org was successfully
verified for 2026/27** and is the source used by the dashboard.
`season=2026` identifies the 2026/27 season. A catalogue entry or a positive
`coverage` flag is not enough: the required endpoints must return actual data.
Sources and limitations: [API discovery](docs/api-discovery.md).

## Alternative provider: football-data.org

Authenticated check on **13 October 2026**: 4 HTTP 200 responses, 20 teams,
380 matches (60 finished with scores), 38 Brighton fixtures and TOTAL standings
with 20 rows. Brighton's ID on this provider is **397**. Results for 2025/26 and
2024/25 were subsequently verified for dashboard comparisons. Advanced statistics
still need verification; the database has yet to be implemented.

A second, independent probe makes at most **4 calls**: Premier League competition
metadata, teams, matches and standings. It validates the season filter and reports
counts, Brighton's presence and the next observed fixture. Actual access is recorded
in the report rather than inferred from the season list alone.

Add the provider token to `.env` (ignored by Git) on a separate line:

```dotenv
FOOTBALL_DATA_TOKEN=your_football_data_token
```

```powershell
python scripts/check_football_data.py --dry-run
python scripts/check_football_data.py --season 2026 --env-file .env
```

`--env-file` reads only `FOOTBALL_DATA_TOKEN`; an existing environment variable
takes precedence. It never uses `API_FOOTBALL_KEY` for this provider.
JSON reports are saved to `reports/football-data-2026-<timestamp>.json`; see
[football-data.org discovery](docs/football-data-discovery.md) for details and limitations.

## Run the probes without external dependencies

Requires Python 3.11 or later. Run these commands from the repository root:

```powershell
python scripts/check_api_coverage.py --dry-run
python -m unittest discover -s tests -v
```

Live verification requires a key from a **direct API-SPORTS Free account**,
available from the [provider dashboard](https://dashboard.api-football.com/).
The client does not support RapidAPI. Set `API_FOOTBALL_KEY` in the process
environment; do not put the token in source code, chat or CLI arguments.
PowerShell example that keeps the token out of command history:

```powershell
$apiKeyInput = Read-Host 'API-Football key' -AsSecureString
$env:API_FOOTBALL_KEY = [System.Net.NetworkCredential]::new('', $apiKeyInput).Password
python scripts/check_api_coverage.py --season 2026
Remove-Item Env:\API_FOOTBALL_KEY
Remove-Variable apiKeyInput
```

`.env.example` documents the variable; **the API-Football probe does not load `.env`**.
The variable must be exported in the same session that starts Python.
PostgreSQL, dbt and Streamlit are not required to run the probes.

The probe makes at most **7 attempts**, spaced at least 6.1 seconds apart,
with `/status` included in the conservative request budget. Reduce the limit with
`--max-requests 3`. It writes JSON and Markdown reports with UTC timestamps to
`reports/`. It does not publish data, schedule jobs or fetch every page.
Running it again repeats the checks and consumes additional quota; reuse existing reports.

Exit codes: `0` checks completed (including empty responses or skipped checks),
`2` missing/invalid configuration, `3` interrupted with partial evidence where
available. **Exit 0 does not prove that the platform is feasible.** Inspect
`outcome`, `coverage_declared`, counts and non-null fields in the JSON report.

## Implemented structure

```text
.github/workflows/ci.yml         # offline checks only; no secrets or API calls
docs/
  architecture.md               # data flow, logical schema, ML and roadmap
  api-discovery.md              # endpoints, interpretation and go/no-go decision
scripts/check_api_coverage.py    # entry point from the checkout
scripts/check_football_data.py   # alternative football-data.org probe
src/football_intelligence/
  api.py                        # HTTP, quota and error classification
  probe.py                      # dependency checks and reports
  football_data.py              # football-data.org v4 client and probe
tests/test_probe.py              # synthetic responses; no live requests
reports/                        # local reports ignored by Git
.state/                         # local ledger and lock, created at runtime
.env.example
pyproject.toml
```

The frontend is in `app/streamlit_app.py`, with charts in `app/charts.py`.
The squad view is in `app/squad_view.py`; `src/football_intelligence/squad.py`
validates players, calculates ages and groups positions into roles.
`src/football_intelligence/dashboard_data.py` handles caching and data access;
`analytics.py` contains calculations that can be tested independently of Streamlit.
Future modules and milestones are described in the [architecture](docs/architecture.md).

The original folder was not a Git repository. To publish it, initialise Git and
connect a GitHub repository of your choice. No remote or push was created
automatically. Workflows will run after the repository is published to GitHub.
