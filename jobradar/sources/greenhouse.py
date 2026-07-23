"""Greenhouse public job board API."""

from __future__ import annotations

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import SourceError, html_to_text, parse_json, register, require

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"


@register("greenhouse")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    (board,) = require(cfg, "board")
    # `content=true` returns every job's HTML description in the one list call.
    params = {"content": "true"} if deep else None
    r = SESSION.get(API.format(board=board), params=params, timeout=TIMEOUT)
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
                description=html_to_text(j.get("content", "")) if deep else "",
            )
        )
    return jobs
