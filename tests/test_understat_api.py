"""New backend defaults and season contracts, without real CSVs or network calls."""
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fastapi.testclient import TestClient
from football_intelligence.web_api import app, get_source
from football_intelligence.understat_data import UnderstatSource
from football_intelligence.understat_live import normalize_live
from football_intelligence.dashboard_client import ApiDashboardSource
from understat_fixtures import NOW, live_payload, write_season


class UnderstatAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        write_season(self.tmp.name)
        self.loader = Mock(side_effect=lambda season, root: normalize_live(live_payload(), season, datetime.fromtimestamp(NOW, timezone.utc)))
        self.source = UnderstatSource(self.tmp.name, clock=lambda: NOW, live_loader=self.loader)
        app.dependency_overrides[get_source] = lambda: self.source
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def test_default_source_no_longer_needs_tokens(self):
        self.assertIsInstance(get_source(), UnderstatSource)

    def test_local_summary_players_standings_and_comparison(self):
        response = self.client.get("/api/v1/seasons/2024/brighton/summary")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["totals"]["xA"], 5.5)
        self.assertEqual(len(self.client.get("/api/v1/seasons/2024/brighton/players").json()["data"]["players"]), 3)
        self.assertEqual(len(self.client.get("/api/v1/seasons/2024/standings").json()["data"]["standings"]), 2)
        self.assertEqual(self.client.get("/api/v1/brighton/comparison").status_code, 200)
        self.loader.assert_not_called()

    def test_live_shared_snapshot_and_remote_client(self):
        def local_open(request, timeout):
            parsed = urlsplit(request.full_url)
            result = self.client.get(parsed.path + ("?" + parsed.query if parsed.query else ""))
            return BytesIO(result.content)
        with patch("football_intelligence.dashboard_client.urlopen", side_effect=local_open):
            remote = ApiDashboardSource("http://localhost:8000")
            self.assertEqual(remote.season(2026).data["team"]["points"], 3)
            self.assertEqual(remote.matches(2026).data["brighton_team_id"], "understat:220")
            self.assertEqual(len(remote.players(2026).data["players"]), 1)
            self.assertEqual(len(remote.comparison().data["rows"]), 2)
        self.loader.assert_called_once()

    def test_current_failure_and_missing_historical_data_have_error_status(self):
        self.loader.side_effect = ConnectionError()
        response = self.client.get("/api/v1/seasons/2026/brighton/summary")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error_code"], "understat_unavailable")
        self.assertEqual(self.client.get("/api/v1/seasons/2020/brighton/summary").status_code, 503)
        self.assertEqual(self.client.get("/api/v1/seasons/1999/brighton/summary").status_code, 422)
