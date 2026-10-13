"""Small read-only API client. No retries, redirects or secret logging."""

from datetime import date, datetime, timezone
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE_URL = "https://v3.football.api-sports.io"


class StopProbe(RuntimeError):
    """Stop safely, retaining evidence collected so far."""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def integer(value):
    try:
        result = int(value)
        return result if result >= 0 else None
    except (ValueError, TypeError):
        return None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def transport(key, endpoint, params):
    request = Request(
        BASE_URL + endpoint + ("?" + urlencode(params) if params else ""),
        headers={"x-apisports-key": key, "Accept": "application/json"},
    )
    opener = build_opener(NoRedirect())
    try:
        response = opener.open(request, timeout=20)
    except HTTPError as error:
        response = error
    with response:
        status = response.code
        headers = {k.lower(): v for k, v in response.headers.items()}
        # A coverage probe has no reason to download unbounded payloads.
        raw = response.read(5_000_001)
    if len(raw) > 5_000_000:
        raise StopProbe("Response exceeds 5 MB; request counted, no retry.")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        payload = None
    return status, headers, payload


class DailyBudget:
    """Conservative local ledger; caller holds a lock for the entire run."""

    def __init__(self, path: Path, limit=80):
        self.path = path
        self.limit = limit

    def reserve(self):
        today = datetime.now(timezone.utc).date().isoformat()
        state = {"date": today, "attempts": 0}
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                if (not isinstance(saved, dict) or type(saved.get("attempts")) is not int
                        or saved["attempts"] < 0):
                    raise ValueError()
                date.fromisoformat(saved["date"])
                if saved.get("date") == today:
                    state = saved
            except (ValueError, TypeError, KeyError):
                raise StopProbe("Local quota ledger invalid; inspect it before continuing.") from None
        if state["attempts"] >= self.limit:
            raise StopProbe("Local daily request ceiling reached (80 attempts).")
        state["attempts"] += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state), encoding="utf-8")
        temporary.replace(self.path)


def classify(status, payload):
    if status in (401, 403):
        return "access_denied"
    if status == 429:
        return "rate_limited"
    if status != 200:
        return "http_error"
    if not isinstance(payload, dict) or "response" not in payload or "errors" not in payload:
        return "invalid_response"
    if payload["errors"]:
        message = json.dumps(payload["errors"]).lower()
        if any(term in message for term in ("ratelimit", "rate limit", "request limit")):
            return "rate_limited"
        if any(term in message for term in ("free plan", "subscription", "access", "token", "api key")):
            return "access_denied"
        return "api_error"
    data = payload["response"]
    if not isinstance(data, (list, dict)):
        return "invalid_response"
    if not data:
        return "empty"
    paging = payload.get("paging") or {}
    if (integer(paging.get("total")) or 1) > 1:
        return "partial"
    return "data_returned"


class Client:
    def __init__(self, key, budget, max_requests=7, reserve=10,
                 send=transport, sleep=time.sleep, monotonic=time.monotonic):
        self.key, self.budget = key, budget
        self.max_requests, self.reserve = max_requests, reserve
        self.send, self.sleep, self.monotonic = send, sleep, monotonic
        self.attempts = 0
        self.remaining = None
        self.interval = 6.1
        self.last_call = None
        self.stop_reason = None
        self.checks = []

    def get(self, endpoint, params):
        if self.stop_reason:
            raise StopProbe(self.stop_reason)
        if self.attempts >= self.max_requests:
            raise StopProbe("Per-run request budget reached.")
        if self.attempts and (self.remaining is None or self.remaining <= self.reserve):
            raise StopProbe("Daily quota unknown or safety reserve reached.")
        if self.last_call is not None:
            self.sleep(max(0, self.interval - (self.monotonic() - self.last_call)))
        self.budget.reserve()  # Persist before I/O, including timeout attempts.
        self.attempts += 1
        self.last_call = self.monotonic()
        check = {"endpoint": endpoint, "params": params, "checked_at": utc_now()}
        self.checks.append(check)
        try:
            status, headers, payload = self.send(self.key, endpoint, params)
        except (URLError, OSError, TimeoutError, StopProbe):
            check["outcome"] = "transport_error"
            raise StopProbe("Transport failure; request counted, no retry.") from None
        headers = {k.lower(): v for k, v in headers.items()}
        check.update(http_status=status, outcome=classify(status, payload))
        check["quota"] = {k: v for k, v in headers.items() if k in (
            "x-ratelimit-requests-limit", "x-ratelimit-requests-remaining",
            "x-ratelimit-limit", "x-ratelimit-remaining",
        )}
        self.remaining = integer(headers.get("x-ratelimit-requests-remaining"))
        minute_limit = integer(headers.get("x-ratelimit-limit"))
        if minute_limit:
            self.interval = max(self.interval, 60 / minute_limit + 0.1)
        if isinstance(payload, dict):
            check["results"] = payload.get("results")
            check["paging"] = payload.get("paging")
            if payload.get("errors"):
                # Redact even if the provider echoes the credential in an error.
                check["errors"] = json.dumps(payload["errors"]).replace(self.key, "[REDACTED]")[:1500]
        if endpoint == "/status" and check["outcome"] == "data_returned":
            data = payload["response"]
            if not isinstance(data, dict):
                raise StopProbe("Unexpected account status format.")
            usage = data.get("requests") or {}
            current, limit = integer(usage.get("current")), integer(usage.get("limit_day"))
            if current is not None and limit is not None:
                # Count the status attempt conservatively, even if provider exempts it.
                status_remaining = max(0, min(limit, 100) - current - 1)
                self.remaining = min(self.remaining, status_remaining) if self.remaining is not None else status_remaining
            sub = data.get("subscription") or {}
            check["subscription"] = {"plan": sub.get("plan"), "active": sub.get("active")}
            check["usage"] = {"current": current, "limit_day": limit}
            # Do not store account names/email or the full status response.
            if str(sub.get("plan", "")).lower() != "free" or sub.get("active") is not True:
                self.stop_reason = "Account is not confirmed active Free; cannot verify Free coverage."
        if integer(headers.get("x-ratelimit-remaining")) == 0:
            self.stop_reason = "Per-minute quota exhausted; no retry."
        if check["outcome"] in ("access_denied", "rate_limited", "http_error", "invalid_response"):
            self.stop_reason = "Stopped after " + check["outcome"] + "; inspect report."
        return payload.get("response") if isinstance(payload, dict) else None, check
