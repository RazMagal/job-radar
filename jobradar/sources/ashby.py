"""Ashby public job board API."""

from __future__ import annotations

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import SourceError, register, require

API = "https://api.ashbyhq.com/posting-api/job-board/{board}"


@register("ashby")
def fetch(cfg: dict) -> list[Job]:
    (board,) = require(cfg, "board")
    r = SESSION.get(API.format(board=board), timeout=TIMEOUT)
    if r.status_code in (400, 404):
        raise SourceError(f"ashby board {board!r} does not exist")
    r.raise_for_status()

    jobs = []
    for j in r.json().get("jobs", []):
        if j.get("isListed") is False:
            continue
        jobs.append(
            Job(
                company=cfg["name"],
                title=j.get("title", ""),
                url=j.get("jobUrl", "") or j.get("applyUrl", ""),
                location=j.get("location", "") or "",
                department=j.get("department", "") or j.get("team", "") or "",
                posted_at=(j.get("publishedAt") or "")[:10],
                source="ashby",
            )
        )
    return jobs
