"""SmartRecruiters public postings API (paginated)."""

from __future__ import annotations

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import SourceError, parse_json, register, require

API = "https://api.smartrecruiters.com/v1/companies/{company}/postings"
PAGE = 100
MAX_PAGES = 20


@register("smartrecruiters")
def fetch(cfg: dict) -> list[Job]:
    (company,) = require(cfg, "board")
    jobs, offset = [], 0

    for _ in range(MAX_PAGES):
        r = SESSION.get(
            API.format(company=company),
            params={"limit": PAGE, "offset": offset},
            timeout=TIMEOUT,
        )
        if r.status_code == 404:
            raise SourceError(f"smartrecruiters company {company!r} does not exist")
        r.raise_for_status()
        payload = parse_json(r, f"smartrecruiters/{company}")
        batch = payload.get("content", [])
        if not batch:
            break

        for j in batch:
            loc = j.get("location") or {}
            where = ", ".join(x for x in (loc.get("city"), loc.get("country")) if x)
            jobs.append(
                Job(
                    company=cfg["name"],
                    title=j.get("name", ""),
                    url=f"https://jobs.smartrecruiters.com/{company}/{j.get('id', '')}",
                    location=where,
                    department=(j.get("department") or {}).get("label", "") or "",
                    posted_at=(j.get("releasedDate") or "")[:10],
                    source="smartrecruiters",
                )
            )

        offset += PAGE
        if offset >= payload.get("totalFound", 0):
            break

    return jobs
