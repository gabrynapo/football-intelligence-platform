"""Local Understat season exports and a cached live current-season snapshot."""

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import time
from zoneinfo import ZoneInfo

import pandas as pd

from .dashboard_data import Dataset, DashboardSource
from .probe import ROOT, exclusive_run
from .api import StopProbe

PLAYER_COLUMNS = ["number", "player", "team", "apps", "min", "goals", "NPG", "a", "xG", "NPxG", "xA",
                  "xGChain", "xGBuildup", "xG90", "NPxG90", "xA90", "xG90xA90", "NPxG90xA90",
                  "xGChain90", "xGBuildup90"]
TEAM_COLUMNS = ["number", "team", "matches", "wins", "draws", "loses", "goals", "ga", "points", "xG",
                "NPxG", "xGA", "NPxGA", "NPxGD", "ppda", "ppda_allowed", "deep", "deep_allowed", "xPTS"]
BRIGHTON_NAMES = {"brighton", "brighton & hove albion", "brighton and hove albion"}
INTEGER_COLUMNS = {"number", "apps", "min", "goals", "NPG", "a", "matches", "wins", "draws", "loses",
                   "ga", "points", "deep", "deep_allowed", "shots", "key_passes", "yellow_cards", "red_cards", "player_id"}
PER90 = {"xG90": ("xG",), "NPxG90": ("NPxG",), "xA90": ("xA",), "xG90xA90": ("xG", "xA"),
         "NPxG90xA90": ("NPxG", "xA"), "xGChain90": ("xGChain",), "xGBuildup90": ("xGBuildup",)}


def current_season(clock=time.time):
    today = datetime.fromtimestamp(clock(), ZoneInfo("Europe/Rome"))
    return today.year if today.month >= 7 else today.year - 1


def clubs(value):
    return [part.strip().casefold() for part in str(value).split(",") if part.strip()]


def is_brighton(value):
    return any(part in BRIGHTON_NAMES for part in clubs(value))


def number(value, column):
    if value is None or pd.isna(value) or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"Invalid numeric value in {column}.")
    result = float(value)
    if not math.isfinite(result) or (column != "NPxGD" and result < 0):
        raise ValueError(f"Invalid numeric value in {column}.")
    if column in INTEGER_COLUMNS:
        if not result.is_integer():
            raise ValueError(f"Expected an integer in {column}.")
        return int(result)
    return result


def normalize_frame(frame, kind):
    required = PLAYER_COLUMNS if kind == "players" else TEAM_COLUMNS
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError("Missing CSV columns: " + ", ".join(sorted(missing)))
    if frame["team"].isna().any():
        raise ValueError("Missing team names.")
    if kind == "players":
        frame = frame[frame["team"].map(is_brighton)].copy()
    records, seen = [], set()
    for raw in frame.to_dict("records"):
        row = {}
        for key, value in raw.items():
            if key in ("team", "player", "position"):
                row[key] = str(value).strip() if not pd.isna(value) else None
            elif key == "multi_club":
                continue
            elif key in required or key in INTEGER_COLUMNS:
                row[key] = number(value, key)
            else:
                row[key] = None if pd.isna(value) else value
        identity = (row.get("player"), row["team"]) if kind == "players" else row["team"]
        if identity in seen or (kind == "players" and not row.get("player")):
            raise ValueError("Missing or duplicate player/team records.")
        seen.add(identity)
        if kind == "players":
            row["multi_club"] = len(clubs(row["team"])) > 1
        else:
            if all(row[k] is not None for k in ("matches", "wins", "draws", "loses")):
                if row["matches"] != row["wins"] + row["draws"] + row["loses"]:
                    raise ValueError("Played matches differ from wins, draws and losses.")
        records.append(row)
    return records


def read_export(path, kind):
    # The supplied Understat exports use semicolons, including comma-separated clubs.
    frame = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    return normalize_frame(frame, kind)


def player_totals(players):
    own = [p for p in players if not p["multi_club"]]
    excluded = len(players) - len(own)
    def total(field):
        values = [p[field] for p in own if p.get(field) is not None]
        return round(sum(values), 6) if values else None
    return {"xA": total("xA"), "player_xG": total("xG"), "goals": total("goals"), "assists": total("a"),
            "xA_complete": bool(players) and not excluded and all(p.get("xA") is not None for p in players),
            "excluded_multi_club": excluded, "brighton_only_players": len(own), "players": len(players)}


class UnderstatSource:
    """Historical reads never use the network; only the calendar's current season is live."""

    def __init__(self, root=ROOT, clock=time.time, live_loader=None):
        self.root, self.clock = Path(root), clock
        self.live_loader = live_loader or load_live_season

    def local_seasons(self):
        found = set()
        for path in (self.root / "data").glob("pl-*.csv"):
            match = re.fullmatch(r"pl-(?:players|standings)_(\d{4})-(\d{4})\.csv", path.name)
            if match and int(match[2]) == int(match[1]) + 1 and 2017 <= int(match[1]) < current_season(self.clock):
                found.add(int(match[1]))
        return sorted(found)

    def catalog(self, refresh=False):
        current = current_season(self.clock)
        return Dataset({"source": "Understat", "currentSeason": {"startDate": f"{current}-07-01"},
                        "seasons": [{"startDate": f"{year}-07-01"} for year in self.local_seasons()]}, None)

    def _historical(self, season):
        data = {"source": "Understat CSV", "season": season, "players": [], "standings": [], "matches": [],
                "match_details_available": False, "notes": []}
        stamps = []
        for kind in ("players", "standings"):
            path = self.root / "data" / f"pl-{kind}_{season}-{season + 1}.csv"
            if not path.exists():
                data["notes"].append(f"No local {kind} CSV is available for {season}/{season + 1}.")
                continue
            data[kind] = read_export(path, kind)
            stamps.append(path.stat().st_mtime)
        if not stamps:
            return Dataset(None, None, "No local CSV files are available for this season.", error_code="missing_data")
        return Dataset(data, datetime.fromtimestamp(max(stamps), timezone.utc).isoformat())

    def _live(self, season, refresh):
        path = self.root / "data" / "cache" / "understat" / f"season-v1-{season}.json"
        cached = DashboardSource._read(path)
        try:
            with exclusive_run(self.root / ".state" / "understat"):
                cached = DashboardSource._read(path)
                now = self.clock()
                if now - cached.get("checked_at", 0) < 60 or (not refresh and now < cached.get("expires_at", 0)):
                    return Dataset(cached.get("data"), cached.get("fetched_at"), cached.get("error"),
                                   bool(cached.get("error") and cached.get("data")), cached.get("error_code"))
                try:
                    data = self.live_loader(season, self.root)
                    if data.get("season") != season:
                        raise ValueError("Understat returned a different season.")
                    result = Dataset(data, datetime.fromtimestamp(self.clock(), timezone.utc).isoformat())
                    ttl = 3600
                except Exception as error:
                    # Scraper exception messages can contain HTML and local paths; do not expose them.
                    message = ("soccerdata is not installed. Install requirements.txt." if isinstance(error, ImportError)
                               else "Understat could not load the current season. Historical CSV data remains available.")
                    result = Dataset(cached.get("data"), cached.get("fetched_at"), message,
                                     bool(cached.get("data")), "understat_unavailable")
                    ttl = 300
                DashboardSource._write(path, {"data": result.data, "fetched_at": result.fetched_at,
                    "error": result.error, "error_code": result.error_code,
                    "checked_at": self.clock(), "expires_at": self.clock() + ttl})
                return result
        except (OSError, StopProbe):
            return Dataset(cached.get("data"), cached.get("fetched_at"),
                           "The Understat cache is busy or unavailable. Try again shortly.",
                           bool(cached.get("data")), "cache_unavailable")

    def season(self, season, refresh=False):
        season = int(season)
        if not 2000 <= season <= current_season(self.clock):
            return Dataset(None, None, "This season has not started or is invalid.", error_code="invalid_season")
        try:
            result = self._live(season, refresh) if season == current_season(self.clock) else self._historical(season)
            if result.data is not None:
                data = dict(result.data)
                data["team"] = next((row for row in data["standings"] if is_brighton(row["team"])), None)
                data["totals"] = player_totals(data["players"])
                result.data = data
            return result
        except (OSError, ValueError, TypeError, KeyError):
            return Dataset(None, None, "Invalid Understat season data. Check the CSV schema, numeric values and duplicate rows.",
                           error_code="invalid_data")

    def _select(self, season, resource, refresh):
        result = self.season(season, refresh)
        if result.data is not None:
            data = result.data
            result.data = {"source": data["source"], "season": season, resource: data[resource],
                           "notes": data.get("notes", []), "match_details_available": data["match_details_available"],
                           "brighton_team_id": data.get("brighton_team_id")}
        return result

    def players(self, season, refresh=False):
        return self._select(season, "players", refresh)

    def standings(self, season, refresh=False):
        return self._select(season, "standings", refresh)

    def matches(self, season, refresh=False):
        return self._select(season, "matches", refresh)

    def squad(self, refresh=False):
        return self.players(current_season(self.clock), refresh)

    def comparison(self, refresh=False):
        rows, notes = [], []
        current = current_season(self.clock)
        for season in self.local_seasons() + [current]:
            if season == current:
                cached = DashboardSource._read(self.root / "data" / "cache" / "understat" / f"season-v1-{season}.json")
                if not cached.get("data"):
                    notes.append(f"{season}/{season + 1}: select this season to load its live Understat data.")
                    continue
                data = dict(cached["data"])
                data["team"] = next((r for r in data["standings"] if is_brighton(r["team"])), None)
                data["totals"] = player_totals(data["players"])
                result = Dataset(data, cached.get("fetched_at"), cached.get("error"),
                                 bool(cached.get("error")) or self.clock() >= cached.get("expires_at", 0))
            else:
                result = self.season(season)
            if not result.data:
                notes.append(f"{season}/{season + 1}: {result.error}")
                continue
            data = result.data
            rows.append({"season": season, **(data["team"] or {}), "xA": data["totals"]["xA"],
                         "xA_complete": data["totals"]["xA_complete"],
                         "excluded_multi_club": data["totals"]["excluded_multi_club"],
                         "source": data["source"], "stale": result.stale})
            if result.error:
                notes.append(f"{season}/{season + 1}: {result.error}")
        return Dataset({"rows": rows, "notes": notes}, None)


def load_live_season(season, root):
    """Isolated soccerdata adapter; no API keys or calls to the former providers."""
    from .understat_live import load
    return load(season, root)
