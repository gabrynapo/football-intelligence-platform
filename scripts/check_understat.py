"""Verify and cache the current Understat season without any API credentials."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from football_intelligence.understat_data import UnderstatSource, current_season

if __name__ == "__main__":
    source = UnderstatSource()
    result = source.season(current_season(), refresh=True)
    if result.data:
        print(f"Season: {result.data['season']}; Brighton players: {len(result.data['players'])}; "
              f"teams: {len(result.data['standings'])}; Brighton fixtures: {len(result.data['matches'])}")
    if result.error:
        print(result.error)
        raise SystemExit(1)
