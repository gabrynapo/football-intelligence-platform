"""Synthetic football-data.org contract tests: never contact the API."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from football_intelligence.football_data import ENDPOINTS, inspect, summarize, token_from_environment
from football_intelligence.api import StopProbe


def season_data(**values):
    return {"competition": {"code": "PL"}, "filters": {"season": "2026"}, **values}


class FootballDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.calls = []
        self.sleeps = []

    def run_probe(self, responses, **kwargs):
        answers = iter(responses)
        def send(token, endpoint, params):
            self.calls.append((endpoint, params))
            return next(answers)
        return inspect("secret-test-token", 2026, self.directory, send=send,
                       sleep=self.sleeps.append, clock=lambda: 100, **kwargs)

    def test_happy_path_four_calls_brighton_and_season(self):
        payloads = [
            {"code": "PL", "id": 2021, "seasons": [{"startDate": "2026-08-01"}]},
            season_data(teams=[{"id": 397, "name": "Brighton & Hove Albion FC"}]),
            season_data(resultSet={"count": 1}, matches=[{
                "status": "FINISHED", "homeTeam": {"id": 397}, "awayTeam": {"id": 1},
                "score": {"fullTime": {"home": 0, "away": 2}}}]),
            season_data(standings=[{"type": "TOTAL", "table": [{"team": {"id": 397}, "points": 0}]}]),
        ]
        report = self.run_probe([(200, {}, data) for data in payloads])
        self.assertIsNone(report["stop_reason"])
        self.assertEqual(report["requests_attempted"], 4)
        self.assertEqual(report["checks"][2]["brighton_match_count"], 1)
        self.assertEqual(report["checks"][2]["completed_with_scores"], 1)
        self.assertEqual(self.calls[1][1], {"season": 2026})
        self.assertTrue(all(value >= 6.1 for value in self.sleeps))

    def test_denial_redacts_token_and_stops(self):
        report = self.run_probe([(403, {}, {"message": "Denied secret-test-token"})])
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn("secret-test-token", json.dumps(report))
        self.assertEqual(report["checks"][0]["outcome"], "access_denied")
        self.assertEqual(report["checks"][1]["outcome"], "not_checked")

    def test_wrong_or_unverifiable_season_rejected(self):
        for data in (season_data(teams=[], filters={"season": "2025"}),
                     {"competition": {"code": "PL"}, "teams": []}):
            with self.assertRaises(StopProbe):
                summarize(ENDPOINTS[1], data, 2026)

    def test_nested_match_season_mismatch(self):
        with self.assertRaises(StopProbe):
            summarize(ENDPOINTS[2], season_data(matches=[{"season": {"startDate": "2025-08-01"}}]), 2026)

    def test_quota_zero_and_429_stop_without_retry(self):
        for answer in ((200, {"X-Requests-Available-Minute": "0"}, {"code": "PL"}),
                       (429, {}, {"message": "rate limit"})):
            self.calls.clear()
            report = self.run_probe([answer])
            self.assertEqual(len(self.calls), 1)
            self.assertIsNotNone(report["stop_reason"])

    def test_timeout_counted_and_safe(self):
        def fail(*args):
            raise URLError("secret-test-token")
        report = inspect("secret-test-token", 2026, self.directory, send=fail)
        self.assertEqual(report["requests_attempted"], 1)
        self.assertEqual(json.loads((self.directory / "quota.json").read_text())["attempts"], 1)
        self.assertNotIn("secret-test-token", json.dumps(report))

    def test_partial_and_empty_are_distinct(self):
        summary, _ = summarize(ENDPOINTS[2], season_data(matches=[], resultSet={"count": 2}), 2026)
        self.assertEqual(summary["outcome"], "partial")
        summary, _ = summarize(ENDPOINTS[2], season_data(matches=[], resultSet={"count": 0}), 2026)
        self.assertEqual(summary["outcome"], "empty")

    def test_budget_and_pacing_persist_across_runs(self):
        for _ in range(2):
            report = self.run_probe([(200, {}, {"code": "PL"})], max_requests=1)
            self.assertIn("budget", report["stop_reason"])
        self.assertEqual(json.loads((self.directory / "quota.json").read_text())["attempts"], 2)
        self.assertGreaterEqual(self.sleeps[-1], 6.1)

    def test_config_is_explicit_and_provider_specific(self):
        path = self.directory / ".env"
        path.write_text('API_FOOTBALL_KEY=wrong-provider\nFOOTBALL_DATA_TOKEN="correct-token"\n')
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(token_from_environment(), "")
            self.assertEqual(token_from_environment(path), "correct-token")
        with patch.dict("os.environ", {"FOOTBALL_DATA_TOKEN": "environment-token"}):
            self.assertEqual(token_from_environment(path), "environment-token")

    def test_duplicate_config_rejected(self):
        path = self.directory / ".env"
        path.write_text("FOOTBALL_DATA_TOKEN=a\nFOOTBALL_DATA_TOKEN=b\n")
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(StopProbe):
            token_from_environment(path)


if __name__ == "__main__":
    unittest.main()
