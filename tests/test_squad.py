"""Roster validation, age calculations and shared API cache behavior."""

from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from football_intelligence.dashboard_data import DashboardSource
from football_intelligence.squad import squad_rows, validate_squad

SQUAD = {"id": 397, "name": "Brighton", "address": "unneeded", "squad": [
    {"id": 1, "name": "Test Keeper", "position": "Goalkeeper", "dateOfBirth": "2000-10-14", "nationality": "England"},
    {"id": 2, "name": "Test Forward", "position": "Centre-Forward", "dateOfBirth": "2002-10-13", "nationality": "Ireland"},
    {"id": 3, "name": "Test Defender", "position": "Defence", "dateOfBirth": None, "nationality": None},
]}


class SquadTests(unittest.TestCase):
    def test_age_at_birthday_and_missing_fields(self):
        rows = {r["id"]: r for r in squad_rows(SQUAD, date(2026, 10, 13))}
        self.assertEqual(rows[1]["age"], 25)
        self.assertEqual(rows[2]["age"], 24)
        self.assertIsNone(rows[3]["age"])
        self.assertEqual(rows[2]["role"], "Forward")
        self.assertEqual(rows[3]["nationality"], "Not available")

    def test_invalid_birthdays_and_unknown_positions(self):
        for birthday in ("bad-date", "2099-01-01", "2000-02-30"):
            payload = {**SQUAD, "squad": [{**SQUAD["squad"][0], "dateOfBirth": birthday, "position": "New role"}]}
            row = squad_rows(payload, date(2026, 10, 13))[0]
            self.assertIsNone(row["age"])
            self.assertIsNone(row["birth_date"])
            self.assertEqual(row["role"], "New role")

    def test_wrong_team_missing_squad_and_duplicates_rejected(self):
        for payload in ({**SQUAD, "id": 1}, {"id": 397}, {**SQUAD, "squad": None},
                        {**SQUAD, "squad": [SQUAD["squad"][0]] * 2}):
            with self.assertRaises(ValueError):
                validate_squad(payload)
        self.assertEqual(validate_squad({"id": 397, "squad": []})["squad"], [])
        self.assertNotIn("address", validate_squad(SQUAD))

    def test_endpoint_cache_cooldown_expiry_and_stale_failure(self):
        with tempfile.TemporaryDirectory() as root:
            now, calls = [10000.0], []
            replies = [(200, {}, SQUAD), (200, {}, SQUAD), (503, {}, {})]
            def send(token, endpoint, params):
                calls.append((endpoint, params))
                return replies.pop(0)
            source = DashboardSource("test", root=root, send=send, clock=lambda: now[0], sleep=lambda seconds: None)
            first = source.squad()
            self.assertIsNone(first.error)
            self.assertNotIn("address", first.data)
            source.squad(refresh=True)
            self.assertEqual(calls, [("/teams/397", {})])
            now[0] += 3601
            source.squad()
            self.assertEqual(len(calls), 1)
            source.squad(refresh=True)
            self.assertEqual(len(calls), 2)
            now[0] += 86401
            failed = source.squad()
            self.assertTrue(failed.stale)
            self.assertEqual(failed.data, first.data)
            self.assertEqual(len(calls), 3)

    def test_squad_uses_shared_rate_limit(self):
        with tempfile.TemporaryDirectory() as root:
            calls = []
            def send(*args):
                calls.append(args)
                return 429, {"Retry-After": "60"}, {}
            source = DashboardSource("test", root=root, send=send, clock=lambda: 10000)
            self.assertEqual(source.squad().error_code, "rate_limited")
            self.assertEqual(source.matches(2026).error_code, "request_stopped")
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
