"""Bounded football-data.org v4 discovery; no ingestion or model training."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from .api import DailyBudget, NoRedirect, StopProbe, integer, utc_now
from .probe import ROOT, exclusive_run

BASE_URL = "https://api.football-data.org/v4"
ENDPOINTS = ("/competitions/PL", "/competitions/PL/teams",
             "/competitions/PL/matches", "/competitions/PL/standings")


def token_from_environment(env_file=None):
    """Read only this provider's token; never reuse the API-SPORTS credential."""
    token = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
    if token or env_file is None:
        return token
    values = []
    for line in Path(env_file).read_text(encoding="utf-8-sig").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == "FOOTBALL_DATA_TOKEN":
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values.append(value.strip())
    if len(values) > 1:
        raise StopProbe("Duplicate FOOTBALL_DATA_TOKEN entries; keep a single value.")
    return values[0] if values else ""


def transport(token, endpoint, params):
    url = BASE_URL + endpoint + ("?" + urlencode(params) if params else "")
    request = Request(url, headers={"X-Auth-Token": token, "Accept": "application/json"})
    try:
        response = build_opener(NoRedirect()).open(request, timeout=20)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read(5_000_001)
        headers = {k.lower(): v for k, v in response.headers.items()}
        status = response.code
    if len(raw) > 5_000_000:
        raise StopProbe("Response too large; no retry.")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        data = None
    return status, headers, data


def classify(status, data):
    if status in (401, 403):
        return "access_denied"
    if status == 429:
        return "rate_limited"
    if status != 200:
        return "http_error"
    if not isinstance(data, dict):
        return "invalid_response"
    if data.get("errorCode") or data.get("message"):
        return "api_error"
    return "data_returned"


def summarize(endpoint, data, season, team_id=None):
    """Keep only evidence relevant to feasibility, not squads or personal data."""
    if endpoint == ENDPOINTS[0]:
        if data.get("code") != "PL":
            raise StopProbe("Unexpected competition in metadata.")
        return {"competition_id": data.get("id"), "name": data.get("name"),
                "current_season": data.get("currentSeason"),
                "catalog_season_start_dates": [s.get("startDate") for s in data.get("seasons", [])]}, team_id
    if data.get("competition", {}).get("code") != "PL":
        raise StopProbe("Unexpected competition in season response.")
    returned = data.get("season", {}).get("startDate")
    filtered = data.get("filters", {}).get("season")
    if returned and str(returned)[:4] != str(season):
        raise StopProbe("Season mismatch; returned data does not match requested year.")
    if filtered is not None and str(filtered) != str(season):
        raise StopProbe("Season filter mismatch.")
    if not returned and filtered is None:
        raise StopProbe("Cannot verify returned season.")
    key = endpoint.rsplit("/", 1)[-1]
    items = data.get(key)
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise StopProbe("Unexpected collection schema.")
    summary = {"returned_count": len(items), "outcome": "data_returned" if items else "empty"}
    if key == "teams":
        candidates = [t for t in items if "brighton" in str(t.get("name", "")).lower()]
        team = candidates[0] if len(candidates) == 1 else {}
        team_id = team.get("id")
        summary["brighton"] = {"id": team_id, "name": team.get("name")}
    elif key == "matches":
        for match in items:
            start = match.get("season", {}).get("startDate")
            if start and str(start)[:4] != str(season):
                raise StopProbe("A match belongs to a different season.")
        count = data.get("resultSet", {}).get("count")
        summary["provider_count"] = count
        if count is not None and count != len(items):
            summary["outcome"] = "partial"
        completed = [m for m in items if m.get("status") == "FINISHED"]
        summary["completed_count"] = len(completed)
        summary["completed_with_scores"] = sum(
            all(type(m.get("score", {}).get("fullTime", {}).get(side)) is int
                for side in ("home", "away")) for m in completed)
        brighton = [m for m in items if team_id is not None and team_id in
                    (m.get("homeTeam", {}).get("id"), m.get("awayTeam", {}).get("id"))]
        summary["brighton_match_count"] = len(brighton)
        now = datetime.now(timezone.utc)
        upcoming = [m for m in brighton if m.get("status") in ("SCHEDULED", "TIMED")
                    and datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")) > now]
        next_match = min(upcoming, key=lambda m: m["utcDate"]) if upcoming else None
        summary["next_brighton_match"] = ({"id": next_match.get("id"), "utcDate": next_match["utcDate"],
                                           "home": next_match.get("homeTeam", {}).get("name"),
                                           "away": next_match.get("awayTeam", {}).get("name")}
                                          if next_match else None)
    elif key == "standings":
        total = [row for group in items if group.get("type") == "TOTAL" for row in group.get("table", [])]
        summary["total_standing_rows"] = len(total)
        summary["brighton"] = [{k: row.get(k) for k in ("position", "playedGames", "points", "goalsFor", "goalsAgainst")}
                               for row in total if team_id is not None and row.get("team", {}).get("id") == team_id]
        if not total:
            summary["outcome"] = "empty"
    return summary, team_id


def inspect(token, season, state_dir, max_requests=4, send=transport, sleep=time.sleep, clock=time.time):
    checks = []
    report = {"provider": "football-data.org", "season": season, "started_at": utc_now(),
              "account_plan": "not_queried", "checks": checks, "stop_reason": None,
              "requests_attempted": 0}
    budget = DailyBudget(state_dir / "quota.json")
    pacing = state_dir / "last-request.json"
    team_id = None
    try:
        for endpoint in ENDPOINTS:
            if report["requests_attempted"] >= max_requests:
                raise StopProbe("Per-run request budget reached.")
            if pacing.exists():
                last = json.loads(pacing.read_text(encoding="utf-8"))
                sleep(max(0, 6.1 - (clock() - float(last))))
            budget.reserve()
            pacing.write_text(json.dumps(clock()), encoding="utf-8")
            params = {} if endpoint == ENDPOINTS[0] else {"season": season}
            check = {"endpoint": endpoint, "params": params, "checked_at": utc_now(), "outcome": "transport_error"}
            checks.append(check)
            report["requests_attempted"] += 1
            status, headers, data = send(token, endpoint, params)
            headers = {k.lower(): v for k, v in headers.items()}
            check.update(http_status=status, outcome=classify(status, data))
            check["quota"] = {k: v for k, v in headers.items() if k in
                              ("x-requests-available-minute", "x-requestcounter-reset", "retry-after")}
            if check["outcome"] != "data_returned":
                if isinstance(data, dict):
                    check["error"] = str(data.get("message", "")).replace(token, "[REDACTED]")[:1000]
                raise StopProbe("Stopped after " + check["outcome"] + "; inspect report.")
            check["outcome"] = "invalid_response"  # Remains inconclusive if validation raises.
            summary, team_id = summarize(endpoint, data, season, team_id)
            check.update(outcome="data_returned", **{k: v for k, v in summary.items() if k != "outcome"})
            check["outcome"] = summary.get("outcome", "data_returned")
            if integer(headers.get("x-requests-available-minute")) == 0 and endpoint != ENDPOINTS[-1]:
                raise StopProbe("Per-minute quota exhausted; no retry.")
    except StopProbe as error:
        report["stop_reason"] = str(error)
    except (URLError, TimeoutError, OSError):
        report["stop_reason"] = "Transport or local state failure; no automatic retry."
    except (TypeError, ValueError, KeyError, AttributeError):
        report["stop_reason"] = "Unexpected response or local state schema; inspect report."
    observed = {c["endpoint"] for c in checks}
    checks.extend({"endpoint": endpoint, "outcome": "not_checked"} for endpoint in ENDPOINTS if endpoint not in observed)
    report["finished_at"] = utc_now()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--max-requests", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--env-file", type=Path, help="Explicit local file; reads only FOOTBALL_DATA_TOKEN")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not 2000 <= args.season <= 2100:
        parser.error("season must be a starting year between 2000 and 2100")
    if args.dry_run:
        print(json.dumps({"provider": BASE_URL, "season": args.season, "max_requests": args.max_requests,
                          "endpoints": ENDPOINTS}, indent=2))
        return 0
    try:
        token = token_from_environment(args.env_file)
        if not token:
            print("FOOTBALL_DATA_TOKEN missing; no request sent.")
            return 2
        state_dir = ROOT / ".state" / "football-data"
        with exclusive_run(state_dir):
            report = inspect(token, args.season, state_dir, args.max_requests)
            directory = ROOT / "reports"
            directory.mkdir(exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            path = directory / f"football-data-{args.season}-{stamp}.json"
            path.write_text(json.dumps(report, indent=2, ensure_ascii=False).replace(token, "[REDACTED]"), encoding="utf-8")
            print(f"Report: {path}\nRequests attempted: {report['requests_attempted']}")
            if report["stop_reason"]:
                print(report["stop_reason"])
                return 3
    except (StopProbe, OSError) as error:
        print(str(error) if isinstance(error, StopProbe) else "Cannot read config or write local state/report.")
        return 3
    return 0
