"""Workable public job-board widget API.

`https://apply.workable.com/api/v1/widget/accounts/{account}` returns the board as JSON,
no auth. Used for companies on Workable (e.g. Vayyar). The list carries the description,
so `scan --deep` works. `board` is the account slug (jobs.workable.com/{account} or
apply.workable.com/{account}).
"""

from __future__ import annotations

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import SourceError, html_to_text, parse_json, register, require

API = "https://apply.workable.com/api/v1/widget/accounts/{account}"


@register("workable")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    (account,) = require(cfg, "board")
    r = SESSION.get(API.format(account=account), params={"details": "true"}, timeout=TIMEOUT)
    if r.status_code == 404:
        raise SourceError(f"workable account {account!r} does not exist")
    r.raise_for_status()

    jobs = []
    for j in parse_json(r, f"workable/{account}").get("jobs") or []:
        where = ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)
        jobs.append(
            Job(
                company=cfg["name"],
                title=j.get("title", ""),
                url=j.get("url", "") or j.get("shortlink", ""),
                location=where,
                department=j.get("department", "") or "",
                posted_at=(j.get("published_on") or j.get("created_at") or "")[:10],
                source="workable",
                description=html_to_text(j.get("description", "")) if deep else "",
            )
        )
    return jobs
