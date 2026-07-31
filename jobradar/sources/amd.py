"""AMD careers public API (Phenom platform).

`careers.amd.com/api/jobs` is clean public JSON, but it has no country filter — only a
geocoded-city `location` — so the whole board is paged (100/req) and filtered client-side
to `country_code == IL`. AMD posts no Israel roles at the moment; this is wired up so they
appear automatically when it does. The list carries the description, so `scan --deep` works.
"""

from __future__ import annotations

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import html_to_text, parse_json, register

API = "https://careers.amd.com/api/jobs"
JOB_URL = "https://careers.amd.com/careers-home/jobs/{req_id}?lang=en-us"
PAGE = 100
MAX_PAGES = 20


@register("amd")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    want = str(cfg.get("country_code", "IL")).upper()
    jobs: list[Job] = []
    for page in range(1, MAX_PAGES + 1):
        params = {
            "page": page,
            "limit": PAGE,
            "sortBy": "relevance",
            "descending": "false",
            "internal": "false",
        }
        r = SESSION.get(API, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = parse_json(r, "amd")
        rows = data.get("jobs") or []
        if not rows:
            break
        for row in rows:
            j = row.get("data", row)
            if str(j.get("country_code") or "").upper() != want:
                continue
            description = ""
            if deep:
                description = html_to_text(
                    " ".join(
                        x
                        for x in (
                            j.get("description"),
                            j.get("qualifications"),
                            j.get("responsibilities"),
                        )
                        if x
                    )
                )
            jobs.append(
                Job(
                    company=cfg["name"],
                    title=j.get("title", ""),
                    url=JOB_URL.format(req_id=j.get("req_id", "") or j.get("slug", "")),
                    location=j.get("full_location", "")
                    or ", ".join(x for x in (j.get("city"), j.get("country")) if x),
                    department=j.get("category", "") or j.get("department", "") or "",
                    posted_at=(j.get("posted_date") or "")[:10],
                    source="amd",
                    description=description,
                )
            )
        if page * PAGE >= (data.get("totalCount") or 0):
            break
    return jobs
