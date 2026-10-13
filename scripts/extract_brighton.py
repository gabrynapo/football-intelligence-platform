"""Extract Brighton rows from local season CSVs, preserving and flagging transfer rows."""
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from football_intelligence.understat_data import UnderstatSource

if __name__ == "__main__":
    source = UnderstatSource()
    destination = source.root / "data" / "processed"
    destination.mkdir(parents=True, exist_ok=True)
    for season in source.local_seasons():
        result = source.players(season)
        if result.error:
            raise SystemExit(f"{season}: {result.error}")
        frame = pd.DataFrame(result.data["players"])
        path = destination / f"brighton-players_{season}-{season + 1}.csv"
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"{path.name}: {len(frame)} Brighton player rows")
