"""Amazon.jobs public search API.

Amazon isn't on a third-party ATS, but amazon.jobs exposes a public JSON search that
takes a server-side location filter — so a plain GET returns just the Israel postings
(Annapurna Labs silicon — Graviton/Trainium chip design + CPU verification — plus AWS and
Amazon Stores), the same shape as the ATS adapters. The list carries the full job
description, so `scan --deep` gets it for free.

`location` and `country` are overridable in config; they default to Israel/ISR.
"""

from __future__ import annotations

from datetime import datetime

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import html_to_text, parse_json, register

API = "https://www.amazon.jobs/en/search.json"
PAGE = 100
MAX_PAGES = 15  # a hard stop; the Israel slice is ~150 postings, so 2-3 pages in practice


def _date(s: str) -> str:
    """amazon.jobs prints the post date as "July 29, 2026"."""
    if not s:
        return ""
    try:
        return datetime.strptime(s.strip(), "%B %d, %Y").date().isoformat()
    except ValueError:
        return ""


@register("amazon")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    # loc_query alone is ignored server-side unless country is set too; both together
    # narrow to Israel (verified — no other-country postings leak in).
    params = {
        "loc_query": cfg.get("location", "Israel"),
        "country": cfg.get("country", "ISR"),
        "result_limit": PAGE,
        "sort": "recent",
    }
    if cfg.get("search_term"):
        params["base_query"] = cfg["search_term"]

    jobs: list[Job] = []
    for page in range(MAX_PAGES):
        params["offset"] = page * PAGE
        r = SESSION.get(API, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        payload = parse_json(r, "amazon")
        batch = payload.get("jobs") or []
        if not batch:
            break
        for j in batch:
            jobs.append(
                Job(
                    company=cfg["name"],
                    title=j.get("title", ""),
                    url="https://www.amazon.jobs" + (j.get("job_path") or ""),
                    location=j.get("normalized_location", "") or j.get("location", ""),
                    department=j.get("job_category", "") or j.get("business_category", "") or "",
                    posted_at=_date(j.get("posted_date", "")),
                    source="amazon",
                    description=html_to_text(j.get("description", "")) if deep else "",
                )
            )
        if (page + 1) * PAGE >= (payload.get("hits") or 0):
            break
    return jobs
