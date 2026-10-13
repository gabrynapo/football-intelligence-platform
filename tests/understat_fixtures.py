"""Synthetic Understat fixtures; no real player data or credentials."""
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc).timestamp()


def player_row(name="Test Albion", team="Brighton", rank=1):
    return {"number": rank, "player": name, "team": team, "apps": 10, "min": 900, "goals": 5, "NPG": 4, "a": 3,
            "xG": 4.25, "NPxG": 3.49, "xA": 2.75, "xGChain": 7.1, "xGBuildup": 2.3,
            "xG90": 0.43, "NPxG90": 0.35, "xA90": 0.28, "xG90xA90": 0.70,
            "NPxG90xA90": 0.62, "xGChain90": 0.71, "xGBuildup90": 0.23}


def team_row(team="Brighton", rank=1):
    return {"number": rank, "team": team, "matches": 38, "wins": 18, "draws": 8, "loses": 12,
            "goals": 72, "ga": 53, "points": 62, "xG": 77.72, "NPxG": 73.16, "xGA": 50.15,
            "NPxGA": 43.98, "NPxGD": 29.18, "ppda": 8.93, "ppda_allowed": 15.01,
            "deep": 362, "deep_allowed": 231, "xPTS": 70.86}


def write_season(root, season=2024, transfers=True):
    directory = Path(root) / "data"
    directory.mkdir(parents=True, exist_ok=True)
    players = [player_row(), player_row("Other Player", "Arsenal", 2), player_row("Another Albion", rank=3)]
    if transfers:
        players.append(player_row("Transfer Player", "Arsenal, Brighton", 4))
    pd.DataFrame(players).to_csv(directory / f"pl-players_{season}-{season + 1}.csv", sep=";", index=False)
    pd.DataFrame([team_row(), team_row("Arsenal", 2)]).to_csv(directory / f"pl-standings_{season}-{season + 1}.csv", sep=";", index=False)


def live_payload():
    history = {"date": "2026-08-23 15:00:00", "result": "w", "h_a": "h", "scored": 2, "missed": 0,
               "pts": 3, "xG": 1.7, "xGA": 0.5, "npxG": 1.7, "npxGA": 0.5, "npxGD": 1.2,
               "ppda": {"att": 60, "def": 10}, "ppda_allowed": {"att": 90, "def": 5},
               "deep": 8, "deep_allowed": 3, "xpts": 2.3}
    away = {**history, "h_a": "a", "result": "l", "scored": 0, "missed": 2, "pts": 0,
            "xG": 0.5, "xGA": 1.7, "npxG": 0.5, "npxGA": 1.7, "npxGD": -1.2, "xpts": 0.4}
    player = {"id": "42", "player_name": "Current Albion", "team_title": "Brighton", "position": "F",
              "games": "1", "time": "90", "goals": "2", "npg": "2", "assists": "1", "xG": "1.7",
              "npxG": "1.7", "xA": "0.75", "xGChain": "2.1", "xGBuildup": "0.2", "shots": "4",
              "key_passes": "3", "yellow_cards": "0", "red_cards": "0"}
    game = {"id": "123", "datetime": "2026-08-23 15:00:00", "h": {"id": "220", "title": "Brighton"},
            "a": {"id": "83", "title": "Arsenal"}, "isResult": True, "goals": {"h": "2", "a": "0"},
            "xG": {"h": "1.7", "a": "0.5"}}
    return {"teamsData": {"220": {"id": "220", "title": "Brighton", "history": [history]},
                          "83": {"id": "83", "title": "Arsenal", "history": [away]}},
            "playersData": [player], "datesData": [game]}
