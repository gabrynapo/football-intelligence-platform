"""Small, version-pinned soccerdata adapter retaining club lists and PPDA components."""

from datetime import datetime, timezone
import os
import time

import pandas as pd
import requests

from .understat_data import PLAYER_COLUMNS, TEAM_COLUMNS, PER90, is_brighton, normalize_frame, number


class BoundedSession(requests.Session):
    """No automatic retries; at most three HTTP requests for a season snapshot."""

    def __init__(self):
        super().__init__()
        self.calls = 0
        self.last_call = 0.0

    def get(self, url, **kwargs):
        if self.calls >= 3:
            raise ConnectionError("Understat snapshot request budget reached.")
        time.sleep(max(0, 1.0 - (time.monotonic() - self.last_call)))
        self.calls += 1
        self.last_call = time.monotonic()
        kwargs.setdefault("timeout", 10)
        response = super().get(url, **kwargs)
        response.raise_for_status()
        return response


def normalize_live(raw, season, now=None):
    now = now or datetime.now(timezone.utc)
    teams, players, dates = raw["teamsData"], raw["playersData"], raw["datesData"]
    if not isinstance(teams, dict) or not teams or not isinstance(players, list) or not isinstance(dates, list):
        raise ValueError("Invalid Understat season payload.")
    standings, fixtures, records = [], [], []
    brighton_id = None
    for team in teams.values():
        title = team["title"]
        if is_brighton(title):
            brighton_id = "understat:" + str(team["id"])
        history = team["history"]
        if not isinstance(history, list):
            raise ValueError("Invalid team history.")
        for game in history:
            day = datetime.fromisoformat(game["date"]).date()
            if not datetime(season, 7, 1).date() <= day < datetime(season + 1, 7, 1).date() or day > now.date():
                raise ValueError("Understat history contains a future or mismatched season match.")
        def total(field):
            values = [number(game.get(field), "NPxGD" if field == "npxGD" else field) for game in history]
            return sum(values) if all(v is not None for v in values) else None
        def ppda(field):
            values = [game.get(field) for game in history]
            if any(not isinstance(v, dict) or v.get("att") is None or v.get("def") is None for v in values):
                return None
            attacks = sum(number(v["att"], field) for v in values)
            defences = sum(number(v["def"], field) for v in values)
            return attacks / defences if defences else None
        row = {"number": None, "team": title, "matches": len(history),
               "wins": sum(g["result"] == "w" for g in history), "draws": sum(g["result"] == "d" for g in history),
               "loses": sum(g["result"] == "l" for g in history), "goals": total("scored"), "ga": total("missed"),
               "points": total("pts"), "xG": total("xG"), "NPxG": total("npxG"), "xGA": total("xGA"),
               "NPxGA": total("npxGA"), "NPxGD": total("npxGD"), "ppda": ppda("ppda"),
               "ppda_allowed": ppda("ppda_allowed"), "deep": total("deep"), "deep_allowed": total("deep_allowed"),
               "xPTS": total("xpts")}
        standings.append(row)
    if brighton_id is None:
        raise ValueError("Brighton was not found in the selected season.")
    standings.sort(key=lambda r: (-(r["points"] or 0), -((r["goals"] or 0) - (r["ga"] or 0)), -(r["goals"] or 0), r["team"]))
    for position, row in enumerate(standings, 1):
        row["number"] = position
    mapping = {"apps": "games", "min": "time", "goals": "goals", "NPG": "npg", "a": "assists",
               "xG": "xG", "NPxG": "npxG", "xA": "xA", "xGChain": "xGChain", "xGBuildup": "xGBuildup",
               "shots": "shots", "key_passes": "key_passes", "yellow_cards": "yellow_cards", "red_cards": "red_cards"}
    for rank, player in enumerate(players, 1):
        if not is_brighton(player["team_title"]):
            continue
        row = {"number": rank, "player": player["player_name"], "team": player["team_title"],
               "position": player.get("position"), "player_id": player["id"]}
        row.update({column: number(player.get(field), column) for column, field in mapping.items()})
        for metric, fields in PER90.items():
            row[metric] = (sum(row[field] for field in fields) * 90 / row["min"]
                           if row["min"] and all(row[field] is not None for field in fields) else None)
        records.append(row)
    seen = set()
    for game in dates:
        if game["id"] in seen:
            raise ValueError("Duplicate Understat fixture.")
        seen.add(game["id"])
        day = datetime.fromisoformat(game["datetime"]).date()
        if not datetime(season, 7, 1).date() <= day < datetime(season + 1, 7, 1).date():
            raise ValueError("Fixture outside the selected season.")
        home = {"id": "understat:" + str(game["h"]["id"]), "name": game["h"]["title"]}
        away = {"id": "understat:" + str(game["a"]["id"]), "name": game["a"]["title"]}
        if brighton_id not in (home["id"], away["id"]):
            continue
        result = game["isResult"]
        if type(result) is not bool or (result and day > now.date()):
            raise ValueError("Invalid fixture result flag.")
        fixtures.append({"id": "understat:" + str(game["id"]), "homeTeam": home, "awayTeam": away,
                         # Understat does not declare a timezone. Keep day precision, never invent a kickoff time.
                         "utcDate": day.isoformat() + "T00:00:00+00:00", "date_precision": "day", "matchday": None,
                         "status": "FINISHED" if result else "SCHEDULED",
                         "score": {"fullTime": {"home": number(game["goals"]["h"], "goals") if result else None,
                                                "away": number(game["goals"]["a"], "goals") if result else None}},
                         "expected_goals": {"home": number(game["xG"]["h"], "xG") if result else None,
                                            "away": number(game["xG"]["a"], "xG") if result else None}})
    if not records and any(r["matches"] for r in standings if is_brighton(r["team"])):
        raise ValueError("Missing Brighton player statistics for completed matches.")
    return {"source": "Understat via soccerdata", "season": season,
            "players": normalize_frame(pd.DataFrame(records, columns=list(dict.fromkeys(PLAYER_COLUMNS + list(mapping) + ["position", "player_id"]))), "players"),
            "standings": normalize_frame(pd.DataFrame(standings, columns=TEAM_COLUMNS), "standings"),
            "matches": fixtures, "brighton_team_id": brighton_id, "match_details_available": True,
            "notes": ["Live standings are calculated from Understat results (points, goal difference, goals scored)."]}


def load(season, root):
    # Set before importing soccerdata, whose configuration creates directories at import time.
    os.environ.setdefault("SOCCERDATA_DIR", str(root / "data" / "cache" / "soccerdata"))
    import soccerdata as sd

    class BoundedUnderstat(sd.Understat):
        @classmethod
        def _all_leagues(cls):
            return sd.Understat._all_leagues()

        def _init_session(self, headers=None):
            return BoundedSession()

    reader = BoundedUnderstat(leagues="ENG-Premier League", seasons=f"{season}/{season + 1}",
                              data_dir=root / "data" / "cache" / "understat" / "raw")
    # This isolated adapter targets soccerdata 1.9.1. Its public player method discards
    # all but the first club on transfer rows; preserve the raw club list instead.
    with reader._session:
        raw = reader._read_league_season(f"https://understat.com/league/EPL/{season}", 1, season, no_cache=True)
    return normalize_live(raw, season)
