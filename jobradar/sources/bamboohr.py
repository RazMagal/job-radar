"""BambooHR public careers API.

`https://{board}.bamboohr.com/careers/list` returns every open req as JSON, no auth —
it's the same endpoint the BambooHR-hosted careers page hydrates from. `board` is the
company's BambooHR subdomain. The list carries no description, but
`/careers/{id}/detail` does, so a describer is registered and `scan --deep` reads it
for matched jobs only.
"""

from __future__ import annotations

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import (
    SourceError,
    html_to_text,
    parse_json,
    register,
    register_describer,
    require,
)

LIST = "https://{board}.bamboohr.com/careers/list"
DETAIL = "https://{board}.bamboohr.com/careers/{id}/detail"
JOB_URL = "https://{board}.bamboohr.com/careers/{id}"


@register("bamboohr")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    (board,) = require(cfg, "board")
    r = SESSION.get(LIST.format(board=board), timeout=TIMEOUT)
    if r.status_code == 404:
        raise SourceError(f"bamboohr board {board!r} does not exist")
    r.raise_for_status()

    jobs = []
    for j in parse_json(r, f"bamboohr/{board}").get("result") or []:
        loc = j.get("location") or {}
        ats = j.get("atsLocation") or {}
        where = ", ".join(
            x for x in (loc.get("city"), loc.get("state"), ats.get("country")) if x
        )
        jobs.append(
            Job(
                company=cfg["name"],
                title=j.get("jobOpeningName", ""),
                url=JOB_URL.format(board=board, id=j.get("id", "")),
                location=where,
                department=j.get("departmentLabel") or "",
                source="bamboohr",
            )
        )
    return jobs


@register_describer("bamboohr")
def describe(cfg: dict, job: Job) -> str:
    board = cfg.get("board", "")
    job_id = job.url.rstrip("/").rsplit("/", 1)[-1]
    if not (board and job_id):
        return ""
    r = SESSION.get(DETAIL.format(board=board, id=job_id), timeout=TIMEOUT)
    if not r.ok:
        return ""
    result = parse_json(r, f"bamboohr/{board}/{job_id}").get("result") or {}
    opening = result.get("jobOpening") or {}
    return html_to_text(opening.get("description") or "")
