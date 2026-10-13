"""Meaningful analytics and cache tests with synthetic provider data."""

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from football_intelligence.analytics import match_rows, summary
from football_intelligence.dashboard_data import DashboardSource


def fixture(mid, date, home, gf, ga, status="FINISHED"):
    return {"id": mid, "utcDate": date, "status": status, "matchday": mid,
            "homeTeam": {"id": 397 if home else 1, "name": "Brighton" if home else "Arsenal"},
            "awayTeam": {"id": 1 if home else 397, "name": "Arsenal" if home else "Brighton"},
            "score": {"fullTime": {"home": gf if home else ga, "away": ga if home else gf}}}


def payload(matches):
    return {"competition": {"code": "PL"}, "filters": {"season": "2026"}, "matches": matches, "resultSet": {"count": len(matches)}}


SAMPLE = payload([
    fixture(2, "2026-08-29T14:00:00Z", False, 1, 1),
    fixture(1, "2026-08-22T14:00:00Z", True, 2, 0),
    fixture(3, "2026-09-05T14:00:00Z", True, 0, 3),
    fixture(4, "2026-11-05T14:00:00Z", True, None, None, "TIMED"),
])


class AnalyticsTests(unittest.TestCase):
    def test_away_scores_and_chronological_cumulative_points(self):
        rows = match_rows(SAMPLE, now=datetime(2026, 10, 1, tzinfo=timezone.utc))
        self.assertEqual([r["result"] for r in rows], ["V", "P", "S", None])
        self.assertEqual([r["cumulative_points"] for r in rows if r["played"]], [3, 4, 4])
        stats = summary(rows)
        self.assertEqual((stats["points"], stats["gf"], stats["ga"], stats["clean_sheets"]), (4, 3, 4, 1))
        self.assertAlmostEqual(stats["ppg"], 4 / 3)

    def test_missing_live_future_and_postponed_scores_do_not_count(self):
        data = payload([fixture(1, "2026-08-01T12:00:00Z", True, None, None),
                        fixture(2, "2026-08-02T12:00:00Z", True, 1, 0, "IN_PLAY"),
                        fixture(3, "2099-08-03T12:00:00Z", True, 1, 0),
                        fixture(4, "2026-08-04T12:00:00Z", True, 0, 0, "POSTPONED")])
        self.assertEqual(summary(match_rows(data))["played"], 0)
        self.assertIsNone(summary(match_rows(data))["ppg"])

    def test_duplicate_matches_rejected(self):
        with self.assertRaises(ValueError):
            match_rows(payload([SAMPLE["matches"][0]] * 2))


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 10_000
        self.calls = 0
        self.responses = [(200, {}, SAMPLE)]

    def source(self):
        def send(*args):
            self.calls += 1
            return self.responses.pop(0)
        def sleep(value):
            self.now += value
        return DashboardSource("test-token", root=self.root, send=send, clock=lambda: self.now, sleep=sleep)

    def test_reruns_and_new_instances_do_not_refetch(self):
        self.assertIsNotNone(self.source().matches(2026).data)
        self.assertIsNotNone(self.source().matches(2026).data)
        self.assertEqual(self.calls, 1)

    def test_refresh_has_cooldown_and_expired_cache_refreshes(self):
        source = self.source()
        source.matches(2026)
        source.matches(2026, refresh=True)
        self.assertEqual(self.calls, 1)
        self.now += 3601
        self.responses = [(200, {}, SAMPLE)]
        source.matches(2026)
        self.assertEqual(self.calls, 2)

    def test_denied_season_negative_cached_without_fabrication(self):
        self.responses = [(403, {}, {"message": "secret provider details"})]
        result = self.source().matches(2025)
        self.assertIsNone(result.data)
        self.assertIn("Accesso negato", result.error)
        self.source().matches(2025)
        self.assertEqual(self.calls, 1)

    def test_stale_cache_label_on_provider_failure(self):
        source = self.source()
        source.matches(2026)
        self.now += 3601
        self.responses = [(503, {}, {})]
        result = source.matches(2026)
        self.assertTrue(result.stale)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.data, SAMPLE)

    def test_rate_limit_blocks_other_resources(self):
        self.responses = [(429, {"Retry-After": "60"}, {})]
        source = self.source()
        source.matches(2026)
        self.assertIsNone(source.standings(2026).data)
        self.assertEqual(self.calls, 1)

    def test_wrong_season_never_cached_as_valid(self):
        self.responses = [(200, {}, {**SAMPLE, "filters": {"season": "2025"}})]
        self.assertIsNone(self.source().matches(2026).data)

    def test_standings_denial_preserves_http_cause_in_cache(self):
        self.responses = [(403, {}, {"message": "Restricted season"})]
        source = self.source()
        first = source.standings(2022)
        second = source.standings(2022)
        self.assertEqual((first.error_code, first.http_status), ("access_denied", 403))
        self.assertEqual((second.error_code, second.http_status), ("access_denied", 403))
        self.assertEqual(self.calls, 1)

    def test_network_failure_does_not_claim_season_unavailable(self):
        def fail(*args):
            raise URLError("private error text")
        source = DashboardSource("test-token", root=self.root, send=fail)
        result = source.standings(2025)
        self.assertEqual(result.error_code, "connection_error")
        self.assertNotIn("private error text", result.error)
        self.assertIsNone(result.http_status)

    def test_empty_standings_is_not_access_denied(self):
        self.responses = [(200, {}, {"competition": {"code": "PL"}, "filters": {"season": "2025"}, "standings": []})]
        result = self.source().standings(2025)
        self.assertIsNone(result.error)
        self.assertEqual(result.http_status, 200)
        self.assertEqual(result.data["standings"], [])


if __name__ == "__main__":
    unittest.main()
