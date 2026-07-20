"""Lever public postings API."""

from __future__ import annotations

from datetime import datetime, timezone

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import SourceError, register, require

API = "https://api.lever.co/v0/postings/{board}?mode=json"


def _date(ms) -> str:
    if not ms:
        return ""
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return ""


@register("lever")
def fetch(cfg: dict) -> list[Job]:
    (board,) = require(cfg, "board")
    r = SESSION.get(API.format(board=board), timeout=TIMEOUT)
    if r.status_code == 404:
        raise SourceError(f"lever board {board!r} does not exist")
    r.raise_for_status()

    jobs = []
    for j in r.json():
        cats = j.get("categories") or {}
        jobs.append(
            Job(
                company=cfg["name"],
                title=j.get("text", ""),
                url=j.get("hostedUrl", "") or j.get("applyUrl", ""),
                location=cats.get("location", "") or "",
                department=cats.get("team", "") or "",
                posted_at=_date(j.get("createdAt")),
                source="lever",
            )
        )
    return jobs
