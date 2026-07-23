"""Source registry. Each source is a callable: (config, deep) -> list[Job].

`deep` (default False) asks the source to also populate Job.description — only used by
`scan --deep` for CV matching. Sources whose list endpoint already carries descriptions
(lever, ashby, greenhouse) fill it in during the fetch; workday can't (its list has no
description), so it registers a per-job describer instead (see DESCRIBERS).
"""

from __future__ import annotations

import html as _html
import re
from typing import Callable, Iterable

from ..models import Job


class SourceError(RuntimeError):
    """A source failed in a way worth reporting to the user (bad board token, 404, ...)."""


Fetcher = Callable[..., Iterable[Job]]
REGISTRY: dict[str, Fetcher] = {}

# Per-job description fetchers, for sources whose list endpoint omits the description.
# describer(cfg, job) -> str. Called only for matched jobs under `scan --deep`.
Describer = Callable[[dict, Job], str]
DESCRIBERS: dict[str, Describer] = {}


def register(name: str):
    def decorator(fn: Fetcher) -> Fetcher:
        REGISTRY[name] = fn
        return fn

    return decorator


def register_describer(name: str):
    def decorator(fn: Describer) -> Describer:
        DESCRIBERS[name] = fn
        return fn

    return decorator


def get(name: str) -> Fetcher:
    try:
        return REGISTRY[name]
    except KeyError:
        raise SourceError(
            f"unknown source type {name!r} (known: {', '.join(sorted(REGISTRY))})"
        ) from None


def get_describer(name: str) -> Describer | None:
    return DESCRIBERS.get(name)


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def html_to_text(s: str) -> str:
    """Unescape entities, drop tags, collapse whitespace. Good enough for keyword
    matching — greenhouse/workday hand back entity-encoded or raw HTML descriptions.

    Unescaped twice on purpose: greenhouse escapes the whole HTML blob, so a literal
    "&" arrives as "&amp;amp;" and one pass would leave "&amp;" sitting in the text.
    """
    if not s:
        return ""
    s = _TAG.sub(" ", _html.unescape(s))
    return _WS.sub(" ", _html.unescape(s)).strip()


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
