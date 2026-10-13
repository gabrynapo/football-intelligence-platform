"""Validate current team rosters and derive descriptive player attributes."""

from datetime import date

from .analytics import BRIGHTON_ID

PLAYER_FIELDS = ("id", "name", "position", "dateOfBirth", "nationality")
ROLES = {
    "Goalkeeper": "Goalkeeper", "Defence": "Defender", "Defender": "Defender",
    "Midfield": "Midfielder", "Midfielder": "Midfielder",
    "Offence": "Forward", "Attacker": "Forward",
    "Centre-Back": "Defender", "Left-Back": "Defender", "Right-Back": "Defender",
    "Defensive Midfield": "Midfielder", "Central Midfield": "Midfielder",
    "Attacking Midfield": "Midfielder", "Left Midfield": "Midfielder",
    "Right Midfield": "Midfielder", "Left Winger": "Forward",
    "Right Winger": "Forward", "Centre-Forward": "Forward", "Second Striker": "Forward",
}


def validate_squad(payload):
    """Keep only required fields; a missing squad is not an empty roster."""
    if payload.get("id") != BRIGHTON_ID or not isinstance(payload.get("squad"), list):
        raise ValueError("Invalid Brighton squad response")
    players, seen = [], set()
    for player in payload["squad"]:
        if not isinstance(player, dict):
            raise ValueError("Invalid player")
        pid = player.get("id")
        if type(pid) is not int or pid <= 0 or pid in seen:
            raise ValueError("Invalid or duplicate player ID")
        if not isinstance(player.get("name"), str) or not player["name"].strip():
            raise ValueError("Missing player name")
        if any(player.get(field) is not None and not isinstance(player[field], str)
               for field in PLAYER_FIELDS[2:]):
            raise ValueError("Invalid player attributes")
        seen.add(pid)
        players.append({field: player.get(field) for field in PLAYER_FIELDS})
    return {"id": BRIGHTON_ID, "name": payload.get("name"), "squad": players}


def squad_rows(payload, as_of):
    """Ages at an explicit observation date; missing/invalid birthdays stay null."""
    rows = []
    for player in validate_squad(payload)["squad"]:
        born, age = None, None
        try:
            born = date.fromisoformat(player["dateOfBirth"])
            if born > as_of:
                born = None
            else:
                age = as_of.year - born.year - ((as_of.month, as_of.day) < (born.month, born.day))
        except (ValueError, TypeError):
            pass
        position = player["position"] or "Not available"
        rows.append({**player, "birth_date": born, "age": age,
                     "role": ROLES.get(position, position),
                     "nationality": player["nationality"] or "Not available"})
    return sorted(rows, key=lambda row: (row["role"], row["name"].casefold()))
