"""Offline Streamlit tests for local CSV seasons and live Understat snapshots."""

from datetime import datetime, timezone
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "app"))

from football_intelligence.understat_data import UnderstatSource
from football_intelligence.understat_live import normalize_live
from understat_fixtures import NOW, live_payload, write_season
from metric_labels import PLAYER_LABELS, TEAM_LABELS


class DashboardUITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        write_season(self.tmp.name, 2024)
        write_season(self.tmp.name, 2023, transfers=False)
        self.loader = Mock(side_effect=lambda season, root: normalize_live(live_payload(), season, datetime.fromtimestamp(NOW, timezone.utc)))
        self.source = UnderstatSource(self.tmp.name, clock=lambda: NOW, live_loader=self.loader)
        self.provider_patch = patch("football_intelligence.understat_data.UnderstatSource", return_value=self.source)
        self.provider_patch.start()
        self.addCleanup(self.provider_patch.stop)
        self.environment = patch.dict(os.environ, {"FOOTBALL_API_BASE_URL": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(ROOT / "app/streamlit_app.py"), default_timeout=20).run()

    def test_current_season_and_historical_totals_without_match_details(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.assertEqual([tab.label for tab in app.tabs], ["Overview", "Matches", "Standings", "Season comparison", "Players"])
        self.assertEqual(app.metric[0].value, "3")
        self.assertTrue(any(m.label == "xA" and m.value == "0.75" for m in app.metric))
        app.sidebar.selectbox[0].select(2024).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, "62")
        self.assertTrue(any(m.label == "Players" and m.value == "3" for m in app.metric))
        self.assertTrue(any(m.label == "xA (partial)" and m.value == "5.50" for m in app.metric))
        self.assertTrue(any("season totals" in msg.value for msg in app.info))
        self.assertEqual(self.loader.call_count, 1)

    def test_player_filters_profile_and_all_csv_columns(self):
        app = self.app()
        app.sidebar.selectbox[0].select(2024).run()
        tables = [element.value for element in app.dataframe]
        player_table = next(frame for frame in tables if "Player" in frame.columns)
        self.assertTrue(set(PLAYER_LABELS[field] for field in ("xGChain90", "NPxG90xA90", "number", "team", "NPG")).issubset(player_table.columns))
        self.assertEqual(len(player_table), 3)
        app.checkbox(key="player_transfers_2024").uncheck().run()
        player_table = next(e.value for e in app.dataframe if "Player" in e.value.columns)
        self.assertEqual(len(player_table), 2)
        app.text_input(key="player_search_2024").input("Another").run()
        self.assertFalse(app.exception)
        self.assertTrue(any(item.value == "Another Albion" for item in app.subheader))
        app.text_input(key="player_search_2024").input("No such player").run()
        self.assertTrue(any("No players match" in item.value for item in app.info))
        self.assertEqual(self.loader.call_count, 1)

    def test_comparison_all_seasons_and_advanced_team_columns(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.assertEqual(app.multiselect[0].value, [2023, 2024, 2026])
        tables = [element.value for element in app.dataframe]
        team_table = next(frame for frame in tables if "PPDA allowed" in frame.columns and "Season" not in frame.columns)
        self.assertTrue(set(TEAM_LABELS.values()).issubset(team_table.columns))
        comparison = next(frame for frame in tables if "Season" in frame.columns)
        self.assertEqual(list(comparison["xA complete"]), [True, False, True])
        app.multiselect[0].set_value([2023]).run()
        comparison = next(e.value for e in app.dataframe if "Season" in e.value.columns)
        self.assertEqual(comparison["Season"].tolist(), ["2023/24"])
        self.assertEqual(self.loader.call_count, 1)

    def test_current_failure_preserves_access_to_history(self):
        self.loader.side_effect = ConnectionError()
        app = self.app()
        self.assertFalse(app.exception)
        self.assertTrue(any("Understat could not load" in msg.value for msg in app.warning))
        self.assertTrue(app.multiselect[0].options)
        app.sidebar.selectbox[0].select(2023).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, "62")
        self.assertTrue(any(m.label == "Players" and m.value == "2" for m in app.metric))

    def test_fastapi_mode_uses_the_same_season_contract(self):
        with patch.dict(os.environ, {"FOOTBALL_API_BASE_URL": "http://127.0.0.1:8000"}), \
                patch("football_intelligence.dashboard_client.ApiDashboardSource", return_value=self.source) as remote:
            app = self.app()
        self.assertFalse(app.exception)
        remote.assert_called_once_with("http://127.0.0.1:8000")
        self.assertEqual(app.metric[0].value, "3")


if __name__ == "__main__":
    unittest.main()
