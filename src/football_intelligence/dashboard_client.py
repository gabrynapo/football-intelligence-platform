"""Optional Streamlit client for the local FastAPI backend."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .dashboard_data import Dataset


class ApiDashboardSource:
    """Same read methods as DashboardSource, with the provider token kept server-side."""

    def __init__(self, base_url: str):
        parsed = urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("FOOTBALL_API_BASE_URL must be an HTTP(S) base URL without credentials or a query.")
        self.base_url = base_url.rstrip("/")

    def _get(self, path: str, refresh: bool) -> Dataset:
        url = self.base_url + path + ("?" + urlencode({"refresh": "true"}) if refresh else "")
        try:
            try:
                reply = urlopen(Request(url, headers={"Accept": "application/json"}), timeout=30)
            except HTTPError as error:
                reply = error
            with reply:
                raw = reply.read(5_000_001)
            if len(raw) > 5_000_000:
                raise ValueError("Backend response too large")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("Invalid backend response")
            return Dataset(**{key: payload[key] for key in
                             ("data", "fetched_at", "error", "stale", "error_code", "http_status")})
        except (URLError, TimeoutError, ConnectionError, OSError):
            return Dataset(None, None, "Unable to reach the FastAPI backend. Check that it is running.", error_code="connection_error")
        except (ValueError, TypeError, KeyError):
            return Dataset(None, None, "The FastAPI backend returned an invalid response.", error_code="invalid_response")

    def catalog(self, refresh=False):
        return self._get("/api/v1/seasons", refresh)

    def matches(self, season, refresh=False):
        return self._get(f"/api/v1/seasons/{int(season)}/matches", refresh)

    def standings(self, season, refresh=False):
        return self._get(f"/api/v1/seasons/{int(season)}/standings", refresh)

    def squad(self, refresh=False):
        return self._get("/api/v1/brighton/squad", refresh)

    def players(self, season, refresh=False):
        return self._get(f"/api/v1/seasons/{int(season)}/brighton/players", refresh)

    def season(self, season, refresh=False):
        return self._get(f"/api/v1/seasons/{int(season)}/brighton/summary", refresh)

    def comparison(self, refresh=False):
        return self._get("/api/v1/brighton/comparison", refresh)
