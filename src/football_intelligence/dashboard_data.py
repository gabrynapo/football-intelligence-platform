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
        if resource not in ("competition", "matches", "standings"):
            raise ValueError("Unsupported dashboard resource")
        endpoint = "/competitions/PL" + ("" if resource == "competition" else "/" + resource)
        params = {} if resource == "competition" else {"season": int(season)}
        path = self.cache / f"{resource}-{season or 'catalog'}.json"
        cached = self._read(path)
        data, fetched_at = cached.get("data"), cached.get("fetched_at")
        if not self.token:
            return Dataset(None, None, "Configura FOOTBALL_DATA_TOKEN nel file .env locale e riapri la pagina.")
        try:
            with exclusive_run(self.state):
                cached = self._read(path)  # Recheck while holding the cross-process lock.
                data, fetched_at = cached.get("data"), cached.get("fetched_at")
                now = self.clock()
                # Even manual refresh has a 60-second cooldown.
                if now - cached.get("checked_at", 0) < 60 or (not refresh and now < cached.get("expires_at", 0)):
                    return Dataset(data, fetched_at, cached.get("error"), bool(cached.get("error") and data),
                                   cached.get("error_code"), cached.get("http_status"))
                blocked = self._read(self.state / "blocked.json").get("until", 0)
                if now < blocked:
                    raise StopProbe("Quota momentaneamente esaurita. Riprova tra circa un minuto.")
                pacing = self.state / "last-request.json"
                if pacing.exists():
                    last = float(json.loads(pacing.read_text(encoding="utf-8")))
                    if not math.isfinite(last) or last > now + 60:
                        raise StopProbe("Stato del limite richieste non valido; controlla l'orologio locale.")
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
                messages = {
                    "access_denied": "Accesso negato: il token o il piano non consentono questi dati. Nessun dato sostitutivo mostrato.",
                    "rate_limited": "Limite richieste raggiunto. Riprova tra circa un minuto.",
                    "http_error": "Il servizio dati non è disponibile in questo momento.",
                    "invalid_response": "La risposta del servizio dati non è valida.",
                    "api_error": "Il servizio non ha accettato la richiesta per questa stagione.",
                }
                error = messages.get(outcome)
                if not error:
                    # Validate competition, collection shape and requested season before caching.
                    summarize(endpoint, payload, season)
                    # Do not retain unnecessary squad/contact/crest fields from the catalog.
                    if resource == "competition":
                        payload = {"id": payload.get("id"), "code": "PL", "name": payload.get("name"),
                                   "currentSeason": payload.get("currentSeason"), "seasons": payload.get("seasons", [])}
                    data, fetched_at = payload, utc_now()
                # Negative cache avoids repeated denied requests on every widget rerun.
                ttl = 60 if outcome in ("rate_limited", "http_error") else (86400 if resource == "competition" else 3600)
                self._write(path, {"data": data, "fetched_at": fetched_at, "checked_at": self.clock(),
                                   "expires_at": self.clock() + ttl, "error": error,
                                   "error_code": outcome if error else None, "http_status": status})
                return Dataset(data, fetched_at, error, bool(error and data), outcome if error else None, status)
        except StopProbe as error:
            # These are local guard/validation messages, never arbitrary provider bodies.
            message = str(error).replace(self.token, "[REDACTED]")
            return Dataset(data, fetched_at, f"Richiesta interrotta: {message}", bool(data), "request_stopped")
        except (URLError, TimeoutError, ConnectionError):
            return Dataset(data, fetched_at, "Connessione a football-data.org non riuscita. Riprova: questo errore non dimostra che la stagione sia esclusa dal piano.", bool(data), "connection_error")
        except OSError:
            return Dataset(data, fetched_at, "Errore di connessione o di accesso alla cache locale. Riprova e controlla i permessi della cartella del progetto.", bool(data), "io_error")
        except (ValueError, TypeError, KeyError, AttributeError):
            return Dataset(data, fetched_at, "Formato della risposta o della cache non valido; impossibile verificare i dati della stagione.", bool(data), "invalid_response")

    def catalog(self, refresh=False):
        return self.get("competition", refresh=refresh)

    def matches(self, season, refresh=False):
        return self.get("matches", season, refresh)

    def standings(self, season, refresh=False):
        return self.get("standings", season, refresh)
