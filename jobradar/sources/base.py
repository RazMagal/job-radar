"""Source registry. Each source is a callable: dict(company config) -> list[Job]."""

from __future__ import annotations

from typing import Callable, Iterable

from ..models import Job


class SourceError(RuntimeError):
    """A source failed in a way worth reporting to the user (bad board token, 404, ...)."""


Fetcher = Callable[[dict], Iterable[Job]]
REGISTRY: dict[str, Fetcher] = {}


def register(name: str):
    def decorator(fn: Fetcher) -> Fetcher:
        REGISTRY[name] = fn
        return fn

    return decorator


def get(name: str) -> Fetcher:
    try:
        return REGISTRY[name]
    except KeyError:
        raise SourceError(
            f"unknown source type {name!r} (known: {', '.join(sorted(REGISTRY))})"
        ) from None


def parse_json(response, label: str):
    """A 200 carrying an HTML block/outage page otherwise surfaces as the useless
    'Expecting value: line 1 column 1 (char 0)'."""
    try:
        return response.json()
    except ValueError:
        ctype = response.headers.get("content-type", "unknown")
        raise SourceError(
            f"{label}: expected JSON but got HTTP {response.status_code} ({ctype}) — "
            "probably a block page or a transient outage; retry"
        ) from None


def require(cfg: dict, *keys: str) -> tuple:
    missing = [k for k in keys if not cfg.get(k)]
    if missing:
        raise SourceError(
            f"{cfg.get('name', '<unnamed>')}: missing required key(s) {', '.join(missing)}"
        )
    return tuple(cfg[k] for k in keys)
