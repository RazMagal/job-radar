"""Workday CXS API — the one most big chip companies (Intel, NVIDIA, Marvell...) use.

Not officially public, but it's the same unauthenticated endpoint the careers site
itself calls from the browser. Pages 20 at a time; that limit is server-enforced.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

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

ENDPOINT = "https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
DETAIL = "https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{path}"
VIEW = "https://{tenant}.{wd}.myworkdayjobs.com/en-US/{site}{path}"
PAGE = 20
MAX_PAGES = 60  # ADI unfiltered is ~940 postings; hitting the cap raises, never truncates

_DAYS = re.compile(r"(\d+)\+?\s*days?", re.I)


def _posted_on(text: str) -> str:
    """Workday reports 'Posted 5 Days Ago', not a date. Convert to an ISO date so
    postings sort sensibly; '30+ Days Ago' floors at 30, which is all it tells us."""
    if not text:
        return ""
    low = text.lower()
    if "today" in low:
        return date.today().isoformat()
    if "yesterday" in low:
        return (date.today() - timedelta(days=1)).isoformat()
    m = _DAYS.search(low)
    if m:
        return (date.today() - timedelta(days=int(m.group(1)))).isoformat()
    return ""


@register("workday")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    # `deep` is a no-op here: the list endpoint has no description, so it's fetched
    # per matched job by the describer below rather than for every posting on the board.
    tenant, site = require(cfg, "tenant", "site")
    wd = cfg.get("wd", "wd1")
    url = ENDPOINT.format(tenant=tenant, wd=wd, site=site)

    jobs, offset = [], 0
    for _ in range(MAX_PAGES):
        r = SESSION.post(
            url,
            json={
                "appliedFacets": cfg.get("facets") or {},
                "limit": PAGE,
                "offset": offset,
                "searchText": cfg.get("search_text", "") or "",
            },
            headers={"Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        # Verified empirically against a known-good board: a bogus site gives 404
        # and a bogus tenant gives 422 — the opposite of what you'd guess.
        if r.status_code == 404:
            raise SourceError(f"workday site {site!r} is wrong for tenant {tenant!r}")
        if r.status_code == 422:
            raise SourceError(
                f"no public workday tenant {tenant!r} on {wd} "
                "(wrong tenant name, wrong wd number, or the company isn't on Workday)"
            )
        if r.status_code == 401:
            raise SourceError(f"workday tenant {tenant!r} is an internal board (401)")
        r.raise_for_status()
        payload = parse_json(r, f"workday/{tenant}/{site}")
        batch = payload.get("jobPostings", [])
        if not batch:
            break

        for j in batch:
            path = j.get("externalPath", "")
            jobs.append(
                Job(
                    company=cfg["name"],
                    title=j.get("title", ""),
                    url=VIEW.format(tenant=tenant, wd=wd, site=site, path=path),
                    location=j.get("locationsText", "") or "",
                    posted_at=_posted_on(j.get("postedOn", "")),
                    source="workday",
                )
            )

        offset += PAGE
        if offset >= payload.get("total", 0):
            break
    else:
        # Exhausting MAX_PAGES with jobs still unfetched must be loud: a silent
        # partial board looks exactly like a complete one.
        raise SourceError(
            f"workday {tenant}/{site}: board exceeds {MAX_PAGES * PAGE} postings "
            f"(got {len(jobs)} of {payload.get('total', '?')}) — raise MAX_PAGES or "
            "add a search_text/facet filter"
        )

    return jobs


@register_describer("workday")
def describe(cfg: dict, job: Job) -> str:
    """One GET per matched job: the CXS detail endpoint carries jobPostingInfo.jobDescription.
    The externalPath is recovered from the view URL we built during the list fetch."""
    tenant, site = cfg["tenant"], cfg["site"]
    wd = cfg.get("wd", "wd1")
    marker = f"/en-US/{site}"
    if marker not in job.url:
        return ""
    path = job.url.split(marker, 1)[1]
    r = SESSION.get(DETAIL.format(tenant=tenant, wd=wd, site=site, path=path), timeout=TIMEOUT)
    if not r.ok:
        return ""
    info = (parse_json(r, f"workday/{tenant}/{site}/detail") or {}).get("jobPostingInfo") or {}
    return html_to_text(info.get("jobDescription", ""))
