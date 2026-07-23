"""Ashby public job board API."""

from __future__ import annotations

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import SourceError, parse_json, register, require

API = "https://api.ashbyhq.com/posting-api/job-board/{board}"


@register("ashby")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    (board,) = require(cfg, "board")
    r = SESSION.get(API.format(board=board), timeout=TIMEOUT)
    if r.status_code in (400, 404):
        raise SourceError(f"ashby board {board!r} does not exist")
    r.raise_for_status()

    jobs = []
    for j in parse_json(r, f"ashby/{board}").get("jobs", []):
        if j.get("isListed") is False:
            continue
        jobs.append(
            Job(
                company=cfg["name"],
                title=j.get("title", ""),
                url=j.get("jobUrl", "") or j.get("applyUrl", ""),
                location=j.get("location", "") or "",
                # The list already carries the full plain-text description.
                description=(j.get("descriptionPlain", "") or "") if deep else "",
                department=j.get("department", "") or j.get("team", "") or "",
                posted_at=(j.get("publishedAt") or "")[:10],
                source="ashby",
            )
        )
    return jobs
