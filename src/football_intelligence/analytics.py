"""Pure Brighton match analytics. Missing scores never become 0-0 draws."""

from datetime import datetime, timezone

BRIGHTON_ID = 397  # Observed football-data.org ID; never an API-SPORTS identifier.


def season_label(year):
    return f"{year}/{str(year + 1)[-2:]}"


def season_options(catalog):
    current = int(catalog["currentSeason"]["startDate"][:4])
    return sorted({int(s["startDate"][:4]) for s in catalog.get("seasons", [])
                   if s.get("startDate") and 2017 <= int(s["startDate"][:4]) <= current} | {current}, reverse=True)


def match_rows(payload, team_id=BRIGHTON_ID, now=None):
    now = now or datetime.now(timezone.utc)
    rows, seen = [], set()
    for match in payload.get("matches", []):
        home, away = match.get("homeTeam") or {}, match.get("awayTeam") or {}
        if team_id not in (home.get("id"), away.get("id")):
            continue
        match_id = match.get("id")
        if match_id is None or match_id in seen:
            raise ValueError("Missing or duplicate match ID.")
        seen.add(match_id)
        home_game = home.get("id") == team_id
        date = datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00")) if match.get("utcDate") else None
        if date and date.tzinfo is None:
            raise ValueError("Match date has no timezone.")
        score = (match.get("score") or {}).get("fullTime") or {}
        goals_for, goals_against = (score.get("home"), score.get("away")) if home_game else (score.get("away"), score.get("home"))
        played = (match.get("status") == "FINISHED" and date is not None and date <= now
                  and all(type(g) is int and g >= 0 for g in (goals_for, goals_against)))
        result = ("W" if goals_for > goals_against else "D" if goals_for == goals_against else "L") if played else None
        rows.append({"id": match_id, "date": date, "matchday": match.get("matchday"),
                     "opponent": (away if home_game else home).get("shortName") or (away if home_game else home).get("name", "To be confirmed"),
                     "venue": "Home" if home_game else "Away", "status": match.get("status"),
                     "gf": goals_for if played else None, "ga": goals_against if played else None,
                     "played": played, "result": result, "points": {"W": 3, "D": 1, "L": 0}.get(result)})
    rows.sort(key=lambda row: (row["date"] or datetime.max.replace(tzinfo=timezone.utc), row["id"]))
    cumulative = gf = ga = games = 0
    recent = []
    for row in rows:
        if row["played"]:
            games += 1
            cumulative += row["points"]
            gf += row["gf"]
            ga += row["ga"]
            recent.append(row["points"])
            row.update(game=games, cumulative_points=cumulative, cumulative_gf=gf, cumulative_ga=ga,
                       rolling_points=sum(recent[-5:]) / len(recent[-5:]))
    return rows


def summary(rows):
    played = [row for row in rows if row["played"]]
    total = len(played)
    points = sum(row["points"] for row in played)
    return {"played": total, "points": points, "ppg": points / total if total else None,
            "wins": sum(row["result"] == "W" for row in played),
            "draws": sum(row["result"] == "D" for row in played),
            "losses": sum(row["result"] == "L" for row in played),
            "gf": sum(row["gf"] for row in played), "ga": sum(row["ga"] for row in played),
            "clean_sheets": sum(row["ga"] == 0 for row in played)}


def total_table(payload):
    return [row for group in (payload or {}).get("standings", [])
            if group.get("type") == "TOTAL" for row in group.get("table", [])]
