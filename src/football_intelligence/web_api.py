"""Local FastAPI facade over the dashboard's shared football-data.org cache."""

from dataclasses import asdict
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Path as PathParameter, Response
from pydantic import BaseModel

from .api import StopProbe
from .dashboard_data import DashboardSource, Dataset
from .football_data import token_from_environment
from .probe import ROOT


class DatasetResponse(BaseModel):
    data: dict | None
    fetched_at: str | None
    error: str | None
    stale: bool
    error_code: str | None
    http_status: int | None


app = FastAPI(
    title="Football Intelligence API",
    description="Brighton and Premier League data from football-data.org, subject to the shared local cache and request limits.",
    version="0.1.0",
)


def get_source() -> DashboardSource:
    """Read credentials on demand; never put them into responses or logs."""
    env_file = Path(ROOT) / ".env"
    try:
        token = token_from_environment(env_file if env_file.exists() else None)
    except (OSError, StopProbe):
        raise HTTPException(status_code=503, detail="Unable to read the local provider configuration.") from None
    return DashboardSource(token)


def deliver(dataset: Dataset, response: Response) -> dict:
    if dataset.error and dataset.data is None:
        response.status_code = {
            "access_denied": 403,
            "rate_limited": 429,
            "api_error": 502,
        }.get(dataset.error_code, 503)
    return asdict(dataset)


@app.get("/health")
def health() -> dict[str, str]:
    """Process health only; does not contact the upstream provider."""
    return {"status": "ok"}


@app.get("/api/v1/seasons", response_model=DatasetResponse)
def seasons(response: Response, refresh: bool = False, source: DashboardSource = Depends(get_source)) -> dict:
    return deliver(source.catalog(refresh=refresh), response)


@app.get("/api/v1/seasons/{season}/matches", response_model=DatasetResponse)
def matches(response: Response, season: int = PathParameter(ge=2000, le=2100),
            refresh: bool = False, source: DashboardSource = Depends(get_source)) -> dict:
    return deliver(source.matches(season, refresh=refresh), response)


@app.get("/api/v1/seasons/{season}/standings", response_model=DatasetResponse)
def standings(response: Response, season: int = PathParameter(ge=2000, le=2100),
              refresh: bool = False, source: DashboardSource = Depends(get_source)) -> dict:
    return deliver(source.standings(season, refresh=refresh), response)


@app.get("/api/v1/brighton/squad", response_model=DatasetResponse)
def squad(response: Response, refresh: bool = False, source: DashboardSource = Depends(get_source)) -> dict:
    return deliver(source.squad(refresh=refresh), response)
