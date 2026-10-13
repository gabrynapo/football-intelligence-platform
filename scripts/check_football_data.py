"""Run the football-data.org probe from a checkout."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from football_intelligence.football_data import main

if __name__ == "__main__":
    raise SystemExit(main())
