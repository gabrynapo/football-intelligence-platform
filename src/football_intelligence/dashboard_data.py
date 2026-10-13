"""On-demand API reads with persistent cache and the probe's shared quota state."""

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import time
from urllib.error import URLError

from .api import DailyBudget, StopProbe, integer, utc_now
from .football_data import classify, summarize, transport
from .probe import ROOT, exclusive_run
from .analytics import BRIGHTON_ID
from .squad import validate_squad

ERROR_MESSAGES = {
    "access_denied": "Access denied: your token or plan does not allow access to this data. No substitute data is shown.",
    "rate_limited": "Request limit reached. Try again in about a minute.",
    "http_error": "The data service is currently unavailable.",
    "invalid_response": "The data service returned an invalid response.",
    "api_error": "The service did not accept the request for this data.",
}


@dataclass
class Dataset:
    data: dict | None
    fetched_at: str | None
    error: str | None = None
    stale: bool = False
    error_code: str | None = None
    http_status: int | None = None


class DashboardSource:
    """Single-host JSON cache; swap this boundary for database reads later."""

    def __init__(self, token, root=ROOT, send=transport, sleep=time.sleep, clock=time.time):
        self.token = token
        self.state = Path(root) / ".state" / "football-data"
        # Separate cache by credential without persisting the credential itself.
        identity = hashlib.sha256(token.encode()).hexdigest()[:16] if token else "missing"
        self.cache = Path(root) / "data" / "cache" / "football-data" / identity
        self.send, self.sleep, self.clock = send, sleep, clock

    @staticmethod
    def _read(path):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)

    def get(self, resource, season=None, refresh=False):
        if resource not in ("competition", "matches", "standings", "squad"):
            raise ValueError("Unsupported dashboard resource")
        endpoint = "/competitions/PL" + ("" if resource == "competition" else "/" + resource)
        params = {} if resource in ("competition", "squad") else {"season": int(season)}
        path = self.cache / f"{resource}-{season or 'catalog'}.json"
        if resource == "squad":
            endpoint, params = f"/teams/{BRIGHTON_ID}", {}
            path = self.cache / f"squad-{BRIGHTON_ID}-current.json"
        cached = self._read(path)
        data, fetched_at = cached.get("data"), cached.get("fetched_at")
        if not self.token:
            return Dataset(None, None, "Set FOOTBALL_DATA_TOKEN in the local .env file and reload the page.")
        try:
            with exclusive_run(self.state):
                cached = self._read(path)  # Recheck while holding the cross-process lock.
                data, fetched_at = cached.get("data"), cached.get("fetched_at")
                now = self.clock()
                # Even manual refresh has a 60-second cooldown.
                if now - cached.get("checked_at", 0) < 60 or (not refresh and now < cached.get("expires_at", 0)):
                    # Resolve messages by code so old cache entries use the current UI language.
                    error = ERROR_MESSAGES.get(cached.get("error_code"), "The previous request failed. Try refreshing this data.") if cached.get("error") else None
                    return Dataset(data, fetched_at, error, bool(error and data),
                                   cached.get("error_code"), cached.get("http_status"))
                blocked = self._read(self.state / "blocked.json").get("until", 0)
                if now < blocked:
                    raise StopProbe("The request quota is temporarily exhausted. Try again in about a minute.")
                pacing = self.state / "last-request.json"
                if pacing.exists():
                    last = float(json.loads(pacing.read_text(encoding="utf-8")))
                    if not math.isfinite(last) or last > now + 60:
                        raise StopProbe("Invalid request limit state; check the local clock.")
                    self.sleep(max(0, 6.1 - (now - last)))
                DailyBudget(self.state / "quota.json").reserve()
                pacing.write_text(json.dumps(self.clock()), encoding="utf-8")
                status, headers, payload = self.send(self.token, endpoint, params)
                headers = {key.lower(): value for key, value in headers.items()}
                remaining = integer(headers.get("x-requests-available-minute", headers.get("x-requestsavailable")))
                if status == 429 or remaining == 0:
                    delay = integer(headers.get("retry-after")) or integer(headers.get("x-requestcounter-reset")) or 60
                    self._write(self.state / "blocked.json", {"until": self.clock() + max(delay, 6.1)})
                outcome = classify(status, payload)
                error = ERROR_MESSAGES.get(outcome)
                if not error:
                    # Validate competition, collection shape and requested season before caching.
                    if resource == "squad":
                        payload = validate_squad(payload)
                    else:
                        summarize(endpoint, payload, season)
                    # Do not retain unnecessary squad/contact/crest fields from the catalog.
                    if resource == "competition":
                        payload = {"id": payload.get("id"), "code": "PL", "name": payload.get("name"),
                                   "currentSeason": payload.get("currentSeason"), "seasons": payload.get("seasons", [])}
                    data, fetched_at = payload, utc_now()
                # Negative cache avoids repeated denied requests on every widget rerun.
                ttl = 60 if outcome in ("rate_limited", "http_error") else (86400 if resource in ("competition", "squad") else 3600)
                self._write(path, {"data": data, "fetched_at": fetched_at, "checked_at": self.clock(),
                                   "expires_at": self.clock() + ttl, "error": error,
                                   "error_code": outcome if error else None, "http_status": status})
                return Dataset(data, fetched_at, error, bool(error and data), outcome if error else None, status)
        except StopProbe as error:
            # These are local guard/validation messages, never arbitrary provider bodies.
            message = str(error).replace(self.token, "[REDACTED]")
            return Dataset(data, fetched_at, f"Request stopped: {message}", bool(data), "request_stopped")
        except (URLError, TimeoutError, ConnectionError):
            return Dataset(data, fetched_at, "Unable to connect to football-data.org. Try again: this error does not mean the season is excluded from your plan.", bool(data), "connection_error")
        except OSError:
            return Dataset(data, fetched_at, "Connection or local cache access error. Try again and check the project folder permissions.", bool(data), "io_error")
        except (ValueError, TypeError, KeyError, AttributeError):
            return Dataset(data, fetched_at, "Invalid response or cache format; unable to verify the requested data.", bool(data), "invalid_response")

    def catalog(self, refresh=False):
        return self.get("competition", refresh=refresh)

    def matches(self, season, refresh=False):
        return self.get("matches", season, refresh)

    def standings(self, season, refresh=False):
        return self.get("standings", season, refresh)

    def squad(self, refresh=False):
        return self.get("squad", refresh=refresh)
