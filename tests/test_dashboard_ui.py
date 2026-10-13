"""Streamlit interaction tests, entirely offline."""

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
from football_intelligence.dashboard_data import Dataset
from test_dashboard import SAMPLE
from test_squad import SQUAD


class FakeSource:
    def __init__(self, token):
        pass

    def catalog(self):
        return Dataset({"currentSeason": {"startDate": "2026-08-21"}, "seasons": [{"startDate": "2025-08-15"}]}, "2026-10-13T12:00:00+00:00")

    def matches(self, season, refresh=False):
        if season == 2025:
            return Dataset(None, None, "Access denied for this season.")
        return Dataset(SAMPLE, "2026-10-13T12:00:00+00:00")

    def standings(self, season, refresh=False):
        return Dataset({"standings": [{"type": "TOTAL", "table": [{"position": 10, "team": {"id": 397, "name": "Brighton"}, "points": 4}]}]}, "2026-10-13T12:00:00+00:00")

    def squad(self, refresh=False):
        return Dataset(SQUAD, "2026-10-13T12:00:00+00:00")


@unittest.skipUnless(importlib.util.find_spec("streamlit"), "Install dashboard extra for UI tests")
class DashboardUITests(unittest.TestCase):
    def test_historical_standings_error_and_targeted_retry(self):
        from streamlit.testing.v1 import AppTest
        calls = []

        class HistoricSource(FakeSource):
            def matches(self, season, refresh=False):
                calls.append(("matches", season, refresh))
                return Dataset(SAMPLE, "2026-10-13T12:00:00+00:00")

            def standings(self, season, refresh=False):
                calls.append(("standings", season, refresh))
                return Dataset(None, None, "Access denied for this season.", error_code="access_denied", http_status=403)

        with patch("football_intelligence.dashboard_data.DashboardSource", HistoricSource):
            app = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=15).run()
            app.sidebar.selectbox[0].select(2025).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Standings 2025/26: Access denied" in w.value for w in app.warning))
            self.assertTrue(any("HTTP 403" in c.value for c in app.caption))
            next(b for b in app.button if b.label == "Reload standings").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(calls[-2:], [("matches", 2025, False), ("standings", 2025, True)])

    def test_render_filters_comparison_and_denied_season(self):
        from streamlit.testing.v1 import AppTest
        with patch("football_intelligence.dashboard_data.DashboardSource", FakeSource):
            app = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=15).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value, "4")
            self.assertEqual([tab.label for tab in app.tabs],
                             ["Overview", "Matches", "Standings", "Season comparison", "Current squad"])
            app.selectbox[0].select("Away").run()
            self.assertFalse(app.exception)
            app.multiselect[0].set_value([2025])
            next(b for b in app.button if b.label == "Compare seasons").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Access denied" in w.value for w in app.warning))
            app.sidebar.selectbox[0].select(2025).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Access denied" in w.value for w in app.warning))
            self.assertTrue(any("not the historical squad" in item.value for item in app.info))
            self.assertTrue(any(m.label == "Squad size" and m.value == "3" for m in app.metric))

    def test_squad_filters_profile_and_targeted_refresh(self):
        from streamlit.testing.v1 import AppTest
        calls = []
        class SquadSource(FakeSource):
            def squad(self, refresh=False):
                calls.append(refresh)
                return super().squad(refresh)
        with patch("football_intelligence.dashboard_data.DashboardSource", SquadSource):
            app = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=15).run()
            app.selectbox(key="squad_role").select("Forward").run()
            self.assertFalse(app.exception)
            self.assertEqual(app.selectbox(key="squad_player").value, 2)
            app.selectbox(key="squad_country").select("England").run()
            self.assertFalse(app.exception)
            self.assertTrue(any("No players" in item.value for item in app.info))
            app.button(key="refresh_squad").click().run()
            self.assertTrue(calls[-1])

    def test_squad_empty_and_denied_do_not_break_season_dashboard(self):
        from streamlit.testing.v1 import AppTest
        for result in (Dataset({"id": 397, "squad": []}, None),
                       Dataset(None, None, "Access denied", error_code="access_denied")):
            with patch("football_intelligence.dashboard_data.DashboardSource", FakeSource), patch.object(FakeSource, "squad", return_value=result):
                app = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=15).run()
                self.assertFalse(app.exception)
                self.assertEqual(app.metric[0].value, "4")
                self.assertTrue(any("empty squad" in item.value for item in app.info) or any("Squad: Access denied" in item.value for item in app.warning))


if __name__ == "__main__":
    unittest.main()
