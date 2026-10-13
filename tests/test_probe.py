"""Offline contract and quota tests. All API responses are synthetic."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from football_intelligence.api import Client, DailyBudget, StopProbe, classify
from football_intelligence.probe import exclusive_run, inspect, main


def envelope(data, errors=None, pages=1):
    return {"errors": errors or {}, "response": data, "results": len(data),
            "paging": {"current": 1, "total": pages}}


def response(data, remaining=90, **kwargs):
    return 200, {"X-RateLimit-Requests-Remaining": str(remaining)}, envelope(data, **kwargs)


ACCOUNT = {"subscription": {"plan": "Free", "active": True},
           "requests": {"current": 1, "limit_day": 100},
           "account": {"email": "private@example.test"}}
MATCH = {"fixture": {"id": 123, "timestamp": 1_700_000_000, "status": {"short": "FT"}},
         "teams": {"home": {"id": 51}, "away": {"id": 1}}, "goals": {"home": 2, "away": 1}}


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "quota.json"

    def client(self, answers, **kwargs):
        self.sent = []
        self.slept = []
        iterator = iter(answers)

        def send(key, endpoint, params):
            self.sent.append((endpoint, params))
            return next(iterator)

        return Client("test-secret", DailyBudget(self.path), send=send,
                      sleep=self.slept.append, monotonic=lambda: 0, **kwargs)

    def test_seven_call_happy_path_and_safe_report(self):
        client = self.client([
            response(ACCOUNT),
            response([{"league": {"id": 39}, "seasons": [{"year": 2026, "coverage": {"standings": True}}]}]),
            response([{"team": {"id": 51, "name": "Brighton"}}]),
            response([MATCH]),
            response([{"league": {"standings": [[{"rank": 1}]]}}]),
            response({"fixtures": {"played": {"total": 1}}, "goals": {}}),
            response([{"team": {"id": 51}, "statistics": [{"type": "Shots", "value": 0}, {"type": "xG", "value": None}]}]),
        ])
        report = inspect(client, 2026)
        self.assertIsNone(report["stop_reason"])
        self.assertEqual(report["requests_attempted"], 7)
        self.assertEqual(report["team_id"], 51)
        self.assertTrue(report["season_in_catalog"])
        self.assertEqual(report["checks"][-1]["statistics"][0]["non_null_types"], ["Shots"])
        self.assertNotIn("private@example", json.dumps(report))
        self.assertNotIn("test-secret", json.dumps(report))
        self.assertTrue(all(delay >= 6.1 for delay in self.slept))
        self.assertEqual(self.sent[-1], ("/fixtures/statistics", {"fixture": 123}))

    def test_empty_season_does_not_claim_access_denied(self):
        client = self.client([response(ACCOUNT)] + [response([])] * 4)
        report = inspect(client, 2026)
        self.assertIsNone(report["stop_reason"])
        self.assertFalse(report["season_in_catalog"])
        self.assertEqual(client.attempts, 5)
        self.assertEqual(report["checks"][-1]["outcome"], "skipped")

    def test_http_200_plan_restriction_stops(self):
        client = self.client([response(ACCOUNT), response([], errors={"plan": "Free plan does not support 2026 test-secret"})])
        report = inspect(client, 2026)
        self.assertEqual(client.attempts, 2)
        self.assertEqual(report["checks"][1]["outcome"], "access_denied")
        self.assertNotIn("test-secret", json.dumps(report))
        self.assertEqual(report["checks"][-1]["outcome"], "not_checked")

    def test_unknown_quota_fails_closed(self):
        client = self.client([(200, {}, envelope({"subscription": ACCOUNT["subscription"]}))])
        report = inspect(client, 2026)
        self.assertEqual(client.attempts, 1)
        self.assertIn("quota unknown", report["stop_reason"])

    def test_status_body_quota_fallback(self):
        client = self.client([(200, {}, envelope(ACCOUNT))])
        client.get("/status", {})
        self.assertEqual(client.remaining, 98)

    def test_remaining_reserve_stops_next_call(self):
        client = self.client([response(ACCOUNT, remaining=10)])
        report = inspect(client, 2026)
        self.assertEqual(client.attempts, 1)
        self.assertIn("reserve", report["stop_reason"])

    def test_per_run_budget(self):
        client = self.client([response(ACCOUNT)], max_requests=1)
        report = inspect(client, 2026)
        self.assertEqual(client.attempts, 1)
        self.assertIn("Per-run", report["stop_reason"])

    def test_paid_plan_cannot_validate_free(self):
        account = {**ACCOUNT, "subscription": {"plan": "Pro", "active": True}}
        report = inspect(self.client([response(account)]), 2026)
        self.assertEqual(report["requests_attempted"], 1)
        self.assertIn("Free", report["stop_reason"])

    def test_rate_limit_no_retry(self):
        client = self.client([(429, {}, envelope([], errors={"rateLimit": "Too many requests"}))])
        report = inspect(client, 2026)
        self.assertEqual(report["requests_attempted"], 1)
        self.assertEqual(report["checks"][0]["outcome"], "rate_limited")

    def test_minute_remaining_zero_stops(self):
        client = self.client([(200, {"x-ratelimit-remaining": "0"}, envelope(ACCOUNT))])
        report = inspect(client, 2026)
        self.assertEqual(client.attempts, 1)
        self.assertIn("Per-minute", report["stop_reason"])

    def test_lower_minute_limit_slows_requests(self):
        client = self.client([(200, {"x-ratelimit-limit": "2"}, envelope(ACCOUNT)), response([])])
        client.get("/status", {})
        client.get("/leagues", {})
        self.assertGreaterEqual(self.slept[0], 30)

    def test_timeout_is_counted_and_not_retried(self):
        client = self.client([])
        def fail(*args):
            raise URLError("secret transport details")
        client.send = fail
        report = inspect(client, 2026)
        self.assertEqual(report["requests_attempted"], 1)
        self.assertEqual(json.loads(self.path.read_text())["attempts"], 1)
        self.assertNotIn("secret transport", json.dumps(report))

    def test_ledger_survives_new_clients(self):
        budget = DailyBudget(self.path, limit=1)
        budget.reserve()
        with self.assertRaises(StopProbe):
            DailyBudget(self.path, limit=1).reserve()

    def test_corrupt_ledger_fails_closed(self):
        for content in ("broken", '{"attempts": "0"}', '{"attempts": 0}',
                        '{"date": "bad-date", "attempts": 0}'):
            self.path.write_text(content)
            with self.assertRaises(StopProbe):
                DailyBudget(self.path).reserve()

    def test_ledger_previous_day_resets(self):
        self.path.write_text(json.dumps({"date": "2000-01-01", "attempts": 80}))
        DailyBudget(self.path).reserve()
        self.assertEqual(json.loads(self.path.read_text())["attempts"], 1)

    def test_lock_blocks_concurrent_run_and_is_cleaned(self):
        directory = Path(self.tmp.name)
        with exclusive_run(directory):
            with self.assertRaises(StopProbe):
                with exclusive_run(directory):
                    pass
        self.assertFalse((directory / "probe.lock").exists())

    def test_future_or_unfinished_fixture_is_not_sampled(self):
        for fixture in ({**MATCH, "fixture": {"id": 1, "timestamp": 4_000_000_000, "status": {"short": "FT"}}},
                        {**MATCH, "fixture": {"id": 1, "timestamp": 1_700_000_000, "status": {"short": "NS"}}}):
            client = self.client([response(ACCOUNT), response([]), response([{"team": {"id": 51, "name": "Brighton"}}]),
                                  response([fixture]), response([]), response({"fixtures": {}})])
            report = inspect(client, 2026)
            self.assertEqual(report["checks"][-1]["outcome"], "skipped")
            self.assertEqual(client.attempts, 6)

    def test_classification_non_json_empty_paginated_and_api_error(self):
        self.assertEqual(classify(200, None), "invalid_response")
        self.assertEqual(classify(200, envelope([])), "empty")
        self.assertEqual(classify(200, envelope([{}], pages=2)), "partial")
        self.assertEqual(classify(200, envelope([], errors={"season": "Invalid value"})), "api_error")
        self.assertEqual(classify(500, {}), "http_error")

    def test_dry_run_and_missing_key_do_not_use_network(self):
        with patch.dict("os.environ", {}, clear=True), patch("football_intelligence.api.transport") as send:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--dry-run"]), 0)
                self.assertEqual(main([]), 2)
            send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
