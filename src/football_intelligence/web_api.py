"""Local FastAPI facade over historical CSVs and the current Understat snapshot."""

from dataclasses import asdict

from fastapi import Depends, FastAPI, Path as PathParameter, Response
from pydantic import BaseModel

from .storage import Dataset
from .understat_data import UnderstatSource


class DatasetResponse(BaseModel):
    data: dict | None
    fetched_at: str | None
    error: str | None
    stale: bool
    error_code: str | None
    http_status: int | None


app = FastAPI(
    title="Football Intelligence API",
    description="Brighton season analytics from local Understat CSVs and a cached live soccerdata snapshot. No provider tokens required.",
    version="0.2.0",
)


def get_source() -> UnderstatSource:
    return UnderstatSource()


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
def seasons(response: Response, refresh: bool = False, source: UnderstatSource = Depends(get_source)) -> dict:
    return deliver(source.catalog(refresh=refresh), response)


@app.get("/api/v1/seasons/{season}/matches", response_model=DatasetResponse)
def matches(response: Response, season: int = PathParameter(ge=2000, le=2100),
            refresh: bool = False, source: UnderstatSource = Depends(get_source)) -> dict:
    return deliver(source.matches(season, refresh=refresh), response)


@app.get("/api/v1/seasons/{season}/standings", response_model=DatasetResponse)
def standings(response: Response, season: int = PathParameter(ge=2000, le=2100),
              refresh: bool = False, source: UnderstatSource = Depends(get_source)) -> dict:
    return deliver(source.standings(season, refresh=refresh), response)


@app.get("/api/v1/brighton/squad", response_model=DatasetResponse)
def squad(response: Response, refresh: bool = False, source: UnderstatSource = Depends(get_source)) -> dict:
    return deliver(source.squad(refresh=refresh), response)


@app.get("/api/v1/seasons/{season}/brighton/players", response_model=DatasetResponse)
def players(response: Response, season: int = PathParameter(ge=2000, le=2100),
            refresh: bool = False, source: UnderstatSource = Depends(get_source)) -> dict:
    return deliver(source.players(season, refresh=refresh), response)


@app.get("/api/v1/seasons/{season}/brighton/summary", response_model=DatasetResponse)
def season_summary(response: Response, season: int = PathParameter(ge=2000, le=2100),
                   refresh: bool = False, source: UnderstatSource = Depends(get_source)) -> dict:
    return deliver(source.season(season, refresh=refresh), response)


@app.get("/api/v1/brighton/comparison", response_model=DatasetResponse)
def comparison(response: Response, refresh: bool = False, source: UnderstatSource = Depends(get_source)) -> dict:
    return deliver(source.comparison(refresh=refresh), response)
