"""Bounded discovery of Premier League coverage, not an ingestion pipeline."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from .api import Client, DailyBudget, StopProbe, utc_now

ROOT = Path(__file__).resolve().parents[2]
PLAN = ["/status", "/leagues", "/teams", "/fixtures", "/standings",
        "/teams/statistics (Brighton)", "/fixtures/statistics (one completed Brighton match)"]


@contextmanager
def exclusive_run(directory):
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / "probe.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError:
        raise StopProbe("Probe lock exists. Check for a running process before removing a stale lock.") from None
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def rows(data):
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def usable(check):
    return check["outcome"] in ("data_returned", "partial")


def inspect(client, season):
    report = {"schema_version": 1, "started_at": utc_now(), "season": season,
              "league_id": 39, "team_name": "Brighton", "checks": client.checks,
              "coverage_declared": {}, "stop_reason": None,
              "scope": "Seven endpoint probes; match statistics sampled on at most one fixture."}
    try:
        _, status = client.get("/status", {})
        if not usable(status):
            raise StopProbe("Account and quota could not be verified.")
        leagues, check = client.get("/leagues", {"id": 39, "season": season})
        metadata = [s for league in rows(leagues) if league.get("league", {}).get("id") == 39
                    for s in rows(league.get("seasons")) if s.get("year") == season] if usable(check) else []
        report["season_in_catalog"] = bool(metadata)
        if metadata:
            report["coverage_declared"] = metadata[0].get("coverage") or {}
        teams, check = client.get("/teams", {"league": 39, "season": season})
        team_rows = rows(teams) if usable(check) else []
        check["team_count"] = len(team_rows)
        brighton = [r["team"] for r in team_rows
                    if "brighton" in str(r.get("team", {}).get("name", "")).lower()]
        team_id = brighton[0].get("id") if len(brighton) == 1 else None
        report["team_id"] = team_id
        fixtures, check = client.get("/fixtures", {"league": 39, "season": season})
        fixture_rows = rows(fixtures) if usable(check) else []
        completed = [r for r in fixture_rows if r.get("fixture", {}).get("status", {}).get("short") == "FT"]
        scored = [r for r in completed if all(isinstance(r.get("goals", {}).get(side), int)
                                            for side in ("home", "away"))]
        check["fixture_count"] = len(fixture_rows)
        check["completed_count"] = len(completed)
        check["completed_with_scores"] = len(scored)
        check["brighton_fixture_count"] = sum(
            team_id is not None and team_id in [r.get("teams", {}).get(s, {}).get("id")
                                               for s in ("home", "away")] for r in fixture_rows)
        now = datetime.now(timezone.utc).timestamp()
        brighton_finished = [r for r in scored if team_id is not None
                             and team_id in [r.get("teams", {}).get(s, {}).get("id") for s in ("home", "away")]]
        candidates = [r for r in brighton_finished
                      if isinstance(r.get("fixture", {}).get("timestamp"), (int, float))
                      and r["fixture"]["timestamp"] <= now]
        sample = max(candidates, key=lambda r: r["fixture"]["timestamp"]) if candidates else None
        standings, check = client.get("/standings", {"league": 39, "season": season})
        check["standing_rows"] = sum(len(group) for r in rows(standings)
                                     for group in r.get("league", {}).get("standings", [])
                                     if isinstance(group, list)) if usable(check) else 0
        if team_id is not None:
            data, check = client.get("/teams/statistics", {"league": 39, "season": season, "team": team_id})
            if usable(check) and isinstance(data, dict):
                check["played_total"] = data.get("fixtures", {}).get("played", {}).get("total")
                check["goals_for"] = data.get("goals", {}).get("for", {}).get("total", {}).get("total")
                check["goals_against"] = data.get("goals", {}).get("against", {}).get("total", {}).get("total")
        else:
            client.checks.append({"endpoint": "/teams/statistics", "outcome": "skipped",
                                  "reason": "Brighton not uniquely identified among returned season teams."})
        if sample:
            data, check = client.get("/fixtures/statistics", {"fixture": sample["fixture"]["id"]})
            check["sample_fixture_id"] = sample["fixture"]["id"]
            if usable(check):
                check["statistics"] = [{"team_id": r.get("team", {}).get("id"),
                                        "non_null_types": [s.get("type") for s in rows(r.get("statistics"))
                                                           if s.get("value") is not None],
                                        "null_types": [s.get("type") for s in rows(r.get("statistics"))
                                                       if s.get("value") is None]} for r in rows(data)]
        else:
            client.checks.append({"endpoint": "/fixtures/statistics", "outcome": "skipped",
                                  "reason": "No completed Brighton fixture with scores and past kickoff available."})
        if client.stop_reason:
            raise StopProbe(client.stop_reason)
    except StopProbe as error:
        report["stop_reason"] = str(error)
    except (KeyError, TypeError, AttributeError, ValueError):
        # Preserve evidence without printing arbitrary server data in tracebacks.
        report["stop_reason"] = "Unexpected provider schema; inspect checks before implementing ingestion."
    report["finished_at"] = utc_now()
    report["requests_attempted"] = client.attempts
    report["daily_remaining_last_observed"] = client.remaining
    observed = {c["endpoint"] for c in client.checks}
    for endpoint in ("/status", "/leagues", "/teams", "/fixtures", "/standings", "/teams/statistics", "/fixtures/statistics"):
        if endpoint not in observed:
            client.checks.append({"endpoint": endpoint, "outcome": "not_checked", "reason": report["stop_reason"]})
    return report


def markdown(report):
    lines = ["# API-Football coverage probe", "", f"Season: {report['season']}/{str(report['season'] + 1)[-2:]}",
             f"Checked at (UTC): {report['finished_at']}", f"Requests attempted: {report['requests_attempted']}", "",
             "| Endpoint | Outcome | HTTP | Results |", "| --- | --- | --- | --- |"]
    for check in report["checks"]:
        lines.append(f"| {check['endpoint']} | {check['outcome']} | {check.get('http_status', '')} | {check.get('results', '')} |")
    lines += ["", "Stop reason: " + (report["stop_reason"] or "none"), "",
              "`data_returned` proves a nonempty response, not completeness or ML readiness.",
              "`empty` does not prove lack of access. `partial` means additional pages exist; none were fetched.",
              "Declared coverage, field-level observations and sanitized errors are in the JSON report.",
              "A single fixture sample cannot establish season-wide statistics coverage.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=2026, help="Starting year, default 2026 (=2026/27)")
    parser.add_argument("--max-requests", type=int, choices=range(1, 8), default=7)
    parser.add_argument("--dry-run", action="store_true", help="Show plan without network, key or state writes")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args(argv)
    if not 2000 <= args.season <= 2100:
        parser.error("season must be a starting year between 2000 and 2100")
    if args.dry_run:
        print(json.dumps({"season": args.season, "league": 39, "max_requests": args.max_requests,
                          "local_daily_ceiling": 80, "daily_reserve": 10, "plan": PLAN}, indent=2))
        return 0
    key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not key:
        print("API_FOOTBALL_KEY is missing. Set it in the process environment; no request sent.")
        return 2
    state_dir = ROOT / ".state"
    try:
        with exclusive_run(state_dir):
            client = Client(key, DailyBudget(state_dir / "quota.json"), args.max_requests)
            report = inspect(client, args.season)
            args.output_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            path = args.output_dir / f"coverage-{args.season}-{stamp}.json"
            # Final redaction also covers unexpected provider text in selected fields.
            path.write_text(json.dumps(report, indent=2, ensure_ascii=False).replace(key, "[REDACTED]"), encoding="utf-8")
            path.with_suffix(".md").write_text(markdown(report).replace(key, "[REDACTED]"), encoding="utf-8")
            print(f"Report: {path}\nRequests attempted: {client.attempts}")
            if report["stop_reason"]:
                print("Stopped: " + report["stop_reason"])
                return 3
    except (StopProbe, OSError) as error:
        print(str(error) if isinstance(error, StopProbe) else "Cannot read/write local state or report; check filesystem permissions.")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
