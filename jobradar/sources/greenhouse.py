"""Greenhouse public job board API."""

from __future__ import annotations

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import SourceError, parse_json, register, require

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"


@register("greenhouse")
def fetch(cfg: dict) -> list[Job]:
    (board,) = require(cfg, "board")
    r = SESSION.get(API.format(board=board), timeout=TIMEOUT)
    if r.status_code == 404:
        raise SourceError(f"greenhouse board {board!r} does not exist")
    r.raise_for_status()

    jobs = []
    for j in parse_json(r, f"greenhouse/{board}").get("jobs", []):
        jobs.append(
            Job(
                company=cfg["name"],
                title=j.get("title", ""),
                url=j.get("absolute_url", ""),
                location=(j.get("location") or {}).get("name", ""),
                posted_at=(j.get("updated_at") or "")[:10],
                source="greenhouse",
            )
        )
    return jobs
