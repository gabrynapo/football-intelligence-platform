"""FastAPI contract tests with no provider or socket calls."""

from io import BytesIO
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.parse import urlsplit
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from football_intelligence.dashboard_client import ApiDashboardSource
from football_intelligence.dashboard_data import DashboardSource, Dataset
from test_dashboard import SAMPLE
from test_squad import SQUAD


@unittest.skipUnless(importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"),
                     "Install api extra for FastAPI tests")
class WebApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from football_intelligence.web_api import app, get_source

        self.app, self.get_source = app, get_source
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.calls = []
        self.now = [10000.0]
        replies = {
            "/competitions/PL": {"id": 2021, "code": "PL", "name": "Premier League",
                                 "currentSeason": {"startDate": "2026-08-21"}, "seasons": [],
                                 "squad": [{"secret": "must not be returned"}]},
            "/competitions/PL/matches": SAMPLE,
            "/competitions/PL/standings": {"competition": {"code": "PL"}, "filters": {"season": "2026"},
                                           "standings": [{"type": "TOTAL", "table": []}]},
            "/teams/397": SQUAD,
        }

        def send(token, endpoint, params):
            self.calls.append((endpoint, params))
            return 200, {}, replies[endpoint]

        source = DashboardSource("test-secret-token", root=self.tmp.name, send=send,
                                 clock=lambda: self.now[0], sleep=lambda delay: self.now.__setitem__(0, self.now[0] + delay))
        app.dependency_overrides[get_source] = lambda: source
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def test_health_validation_cache_refresh_and_response_contract(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/api/v1/seasons/1999/matches").status_code, 422)
        self.assertEqual(self.calls, [])

        responses = [self.client.get(path) for path in (
            "/api/v1/seasons", "/api/v1/seasons/2026/matches",
            "/api/v1/seasons/2026/standings", "/api/v1/brighton/squad")]
        self.assertTrue(all(item.status_code == 200 for item in responses))
        self.assertEqual([endpoint for endpoint, _ in self.calls],
                         ["/competitions/PL", "/competitions/PL/matches", "/competitions/PL/standings", "/teams/397"])
        self.assertEqual(self.calls[1][1], {"season": 2026})
        self.assertEqual(self.calls[3][1], {})
        self.assertEqual(len(responses[3].json()["data"]["squad"]), 3)
        self.assertEqual(set(responses[0].json()),
                         {"data", "fetched_at", "error", "stale", "error_code", "http_status"})
        self.assertNotIn("test-secret-token", "".join(item.text for item in responses))
        self.assertNotIn("must not be returned", responses[0].text)
        self.client.get("/api/v1/seasons/2026/matches?refresh=true")
        self.assertEqual(len(self.calls), 4)  # Shared 60-second cooldown.

    def test_provider_denial_and_stale_data_status(self):
        class FailingSource:
            def squad(self, refresh=False):
                return Dataset(None, None, "Access denied.", error_code="access_denied", http_status=403)

            def matches(self, season, refresh=False):
                return Dataset(SAMPLE, "2026-10-13T00:00:00+00:00", "Provider unavailable.", True,
                               "http_error", 503)

        self.app.dependency_overrides[self.get_source] = lambda: FailingSource()
        denied = self.client.get("/api/v1/brighton/squad")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["error_code"], "access_denied")
        stale = self.client.get("/api/v1/seasons/2026/matches")
        self.assertEqual(stale.status_code, 200)
        self.assertTrue(stale.json()["stale"])

    def test_streamlit_client_reads_backend_envelope_and_error(self):
        class MemoryReply(BytesIO):
            pass

        def in_process_open(request, timeout):
            path = urlsplit(request.full_url)
            response = self.client.get(path.path + ("?" + path.query if path.query else ""))
            if response.status_code >= 400:
                raise HTTPError(request.full_url, response.status_code, "Backend error", {}, MemoryReply(response.content))
            return MemoryReply(response.content)

        remote = ApiDashboardSource("http://127.0.0.1:8000")
        with patch("football_intelligence.dashboard_client.urlopen", side_effect=in_process_open):
            self.assertEqual(remote.matches(2026).data, SAMPLE)
            self.assertEqual(len(remote.squad().data["squad"]), 3)
            self.assertEqual(remote.catalog().data["code"], "PL")
            self.app.dependency_overrides[self.get_source] = lambda: type("Denied", (), {
                "squad": lambda self, refresh=False: Dataset(None, None, "Access denied.",
                                                               error_code="access_denied", http_status=403)})()
            self.assertEqual(remote.squad().error_code, "access_denied")

    def test_invalid_backend_url(self):
        for url in ("", "backend:8000", "http://user:pass@localhost:8000", "http://localhost:8000?token=x"):
            with self.assertRaises(ValueError):
                ApiDashboardSource(url)


if __name__ == "__main__":
    unittest.main()
