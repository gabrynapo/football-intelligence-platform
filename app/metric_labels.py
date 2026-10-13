"""English display names for every field in the supplied Understat exports."""

PLAYER_LABELS = {
    "number": "Source row", "player": "Player", "team": "Club(s)", "apps": "Apps", "min": "Minutes",
    "goals": "Goals", "NPG": "Non-penalty goals", "a": "Assists", "xG": "xG", "NPxG": "Non-penalty xG",
    "xA": "xA", "xGChain": "xGChain", "xGBuildup": "xGBuildup", "xG90": "xG / 90",
    "NPxG90": "NPxG / 90", "xA90": "xA / 90", "xG90xA90": "(xG + xA) / 90",
    "NPxG90xA90": "(NPxG + xA) / 90", "xGChain90": "xGChain / 90", "xGBuildup90": "xGBuildup / 90",
    "multi_club": "Multiple clubs", "position": "Position", "player_id": "Understat player ID",
    "shots": "Shots", "key_passes": "Key passes", "yellow_cards": "Yellow cards", "red_cards": "Red cards",
}
TEAM_LABELS = {
    "number": "Pos", "team": "Team", "matches": "Played", "wins": "W", "draws": "D", "loses": "L",
    "goals": "GF", "ga": "GA", "points": "Points", "xG": "xG", "NPxG": "Non-penalty xG", "xGA": "xGA",
    "NPxGA": "Non-penalty xGA", "NPxGD": "Non-penalty xG difference", "ppda": "PPDA",
    "ppda_allowed": "PPDA allowed", "deep": "Deep completions", "deep_allowed": "Deep completions allowed",
    "xPTS": "Expected points",
}
