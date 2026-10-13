"""Small local storage primitives shared by the Understat source and API facade."""

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Dataset:
    data: dict | None
    fetched_at: str | None
    error: str | None = None
    stale: bool = False
    error_code: str | None = None
    http_status: int | None = None


class LockUnavailable(RuntimeError):
    """Another local process is already refreshing this resource."""


def read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


@contextmanager
def exclusive_run(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / "refresh.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError:
        raise LockUnavailable("Another local Understat refresh is already running.") from None
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)
