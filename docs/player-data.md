# Brighton player data

The dashboard takes historical player data from the local files named
`data/pl-players_YYYY-YYYY.csv`. The `team` field is parsed as a comma-separated
club list and only rows containing Brighton are shown. The original source columns
are retained:

| Group | Fields |
| --- | --- |
| Usage | `apps`, `min` |
| Output | `goals`, `NPG`, `a` |
| Expected output | `xG`, `NPxG`, `xA` |
| Possession contribution | `xGChain`, `xGBuildup` |
| Rates | `xG90`, `NPxG90`, `xA90`, `xG90xA90`, `NPxG90xA90`, `xGChain90`, `xGBuildup90` |

The live current season is fetched via `soccerdata.Understat` and contains the
same core fields plus Understat position, player ID, shots, key passes and cards.
The adapter validates season, exact Brighton club membership, required fields,
numeric values, duplicate records and fixture boundaries before data reaches the
interface.

## Attribution rule

Rows covering more than one club are retained for transparency but cannot be split
reliably from a season aggregate. They receive `multi_club=true`; player charts and
Brighton-only totals exclude them. Therefore a season with combined rows reports
partial xA and player xG. This protects club totals from being overstated.

The helper below materializes the Brighton tuples for all local seasons without
changing the source files:

```powershell
.venv\Scripts\python.exe scripts\extract_brighton.py
```

It writes `data/processed/brighton-players_YYYY-YYYY.csv`, preserving source fields
and adding the attribution flag. The directory is ignored by Git.

## Interpretation

`xG` and `xA` are expected-goal and expected-assist values supplied by Understat.
`NPxG` and `NPG` exclude penalties. `xGChain` measures expected goals in possessions
where the player participated; `xGBuildup` measures earlier contribution and excludes
the final shot and key pass. These possession metrics overlap between players and
must never be summed as a team total. Per-90 fields are rates and are not season totals.

This is descriptive analysis. Historic season aggregates are not point-in-time
features and must not be used for predictive training before a justified cutoff.
