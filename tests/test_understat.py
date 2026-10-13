"""Understat data contracts, historical isolation, transfer attribution and live caching."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from football_intelligence.understat_data import UnderstatSource, current_season, normalize_frame, player_totals, read_export
from football_intelligence.understat_live import normalize_live, load
from understat_fixtures import NOW, live_payload, player_row, write_season


class UnderstatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = [NOW]
        self.loader = Mock(side_effect=lambda season, root: normalize_live(live_payload(), season,
                           datetime.fromtimestamp(self.now[0], timezone.utc)))
        self.source = UnderstatSource(self.root, clock=lambda: self.now[0], live_loader=self.loader)

    def test_csv_only_brighton_with_transfer_rows_and_all_original_values(self):
        write_season(self.root)
        result = self.source.season(2024)
        self.assertIsNone(result.error)
        self.assertEqual(len(result.data["players"]), 3)
        self.assertEqual(result.data["players"][0]["xG90"], 0.43)  # Preserve supplied rounding.
        self.assertEqual(result.data["totals"]["xA"], 5.5)
        self.assertFalse(result.data["totals"]["xA_complete"])
        self.assertEqual(result.data["team"]["xG"], 77.72)  # Team xG is not summed player xG.
        self.assertFalse(result.data["match_details_available"])
        self.source.comparison()
        self.loader.assert_not_called()

    def test_exact_club_membership_and_duplicate_validation(self):
        frame = pd.DataFrame([player_row(), player_row("Wrong", "Not Brighton", 2),
                              player_row("Transferred", "Brighton, Newcastle United", 3)])
        rows = normalize_frame(frame, "players")
        self.assertEqual([r["player"] for r in rows], ["Test Albion", "Transferred"])
        self.assertTrue(rows[1]["multi_club"])
        with self.assertRaises(ValueError):
            normalize_frame(pd.concat([frame, frame]), "players")

    def test_missing_negative_and_nonfinite_values_are_not_zero(self):
        row = player_row()
        row["xA"] = None
        totals = player_totals(normalize_frame(pd.DataFrame([row]), "players"))
        self.assertIsNone(totals["xA"])
        self.assertFalse(totals["xA_complete"])
        for value in (-1, float("inf"), "invalid"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_frame(pd.DataFrame([{**row, "xG": value}]), "players")

    def test_corrupt_or_missing_historical_files_never_fetch_live(self):
        self.assertEqual(self.source.season(2023).error_code, "missing_data")
        write_season(self.root)
        (self.root / "data/pl-players_2024-2025.csv").write_text("wrong;columns\na;b\n")
        self.assertEqual(self.source.season(2024).error_code, "invalid_data")
        self.loader.assert_not_called()

    def test_current_season_one_snapshot_cache_and_refresh_cooldown(self):
        first = self.source.season(2026)
        self.assertEqual(first.data["totals"]["xA"], 0.75)
        self.assertEqual(first.data["team"]["ppda"], 6.0)
        self.assertEqual(first.data["players"][0]["xG90"], 1.7)
        self.source.players(2026)
        self.source.matches(2026)
        self.source.standings(2026, refresh=True)
        self.source.comparison()
        self.assertEqual(self.loader.call_count, 1)
        self.now[0] += 61
        self.source.season(2026, refresh=True)
        self.assertEqual(self.loader.call_count, 2)

    def test_expired_snapshot_failure_keeps_stale_copy_and_negative_cache(self):
        original = self.source.season(2026)
        self.now[0] += 3601
        self.loader.side_effect = ConnectionError("private provider details")
        result = self.source.season(2026)
        self.assertTrue(result.stale)
        self.assertEqual(result.fetched_at, original.fetched_at)
        self.assertNotIn("private", result.error)
        self.source.season(2026)
        self.assertEqual(self.loader.call_count, 2)
        self.assertTrue(self.source.comparison().data["rows"][0]["stale"])

    def test_no_snapshot_failure_still_allows_historical_comparison(self):
        write_season(self.root)
        self.loader.side_effect = ConnectionError()
        self.assertIsNone(self.source.season(2026).data)
        self.assertEqual(self.source.comparison().data["rows"][0]["season"], 2024)
        self.assertEqual(self.loader.call_count, 1)

    def test_season_boundary_uses_rome_calendar_and_future_seasons_are_blocked(self):
        for timestamp, expected in (("2026-06-30T21:00:00+00:00", 2025), ("2026-06-30T23:00:00+00:00", 2026)):
            self.assertEqual(current_season(lambda: datetime.fromisoformat(timestamp).timestamp()), expected)
        self.assertIsNone(self.source.season(2027).data)
        self.loader.assert_not_called()

    def test_live_preserves_multi_club_names_and_rejects_future_results(self):
        raw = live_payload()
        raw["playersData"][0]["team_title"] = "Arsenal,Brighton"
        data = normalize_live(raw, 2026, datetime.fromtimestamp(NOW, timezone.utc))
        self.assertTrue(data["players"][0]["multi_club"])
        self.assertEqual(data["players"][0]["team"], "Arsenal,Brighton")
        raw["datesData"][0]["datetime"] = "2027-01-01 12:00:00"
        with self.assertRaises(ValueError):
            normalize_live(raw, 2026, datetime.fromtimestamp(NOW, timezone.utc))

    def test_soccerdata_adapter_uses_one_season_resource_and_bounded_session(self):
        def close_test_logs():
            logger = logging.getLogger()
            for handler in logger.handlers[:]:
                filename = getattr(handler, "baseFilename", None)
                if filename and Path(filename).is_relative_to(self.root):
                    logger.removeHandler(handler)
                    handler.close()
        self.addCleanup(close_test_logs)
        raw = live_payload()
        response = Mock()
        response.content = json.dumps({"teams": raw["teamsData"], "players": raw["playersData"], "dates": raw["datesData"]}).encode()
        with patch("football_intelligence.understat_live.BoundedSession.get", return_value=response) as get:
            result = load(2026, self.root)
        self.assertEqual(result["season"], 2026)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list[-1].args[0], "https://understat.com/getLeagueData/EPL/2026")


if __name__ == "__main__":
    unittest.main()
