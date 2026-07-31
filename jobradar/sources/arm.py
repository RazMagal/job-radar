"""Arm careers — HTML only (Radancy/TalentBrew), no clean JSON feed.

Arm has no public JSON job list; the location-filtered results page
`careers.arm.com/search-jobs/{location}` is server-rendered HTML, so this parses the job
cards out of it. It's the one scraper here, kept deliberately narrow (a single documented
card shape) and isolated — if the markup changes it fails loudly for this board alone.
Arm's Israel roles are a handful of Ra'anana hardware-verification positions.
"""

from __future__ import annotations

import re

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import SourceError, html_to_text, register

SEARCH = "https://careers.arm.com/search-jobs/{location}"
BASE = "https://careers.arm.com"
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

# <a class="... job-card__title ..." href="/job/raanana/senior-gpu-verification-engineer/33099/9295..." data-job-id="9295...">Title</a>
_CARD = re.compile(r'<a\b[^>]*class="[^"]*job-card__title[^"]*"[^>]*>(.*?)</a>', re.S)
_HREF = re.compile(r'href="([^"]+)"')


@register("arm")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    location = cfg.get("location", "Israel")
    r = SESSION.get(
        SEARCH.format(location=location), headers={"User-Agent": BROWSER_UA}, timeout=TIMEOUT
    )
    r.raise_for_status()
    html = r.text
    # Scope to the real results list — the page also renders a sibling "recommended jobs"
    # <ul data-save-jobs> (other countries) and employee-story links that share the card
    # class, which would otherwise leak in.
    start = html.find('id="search-results-jobs"')
    if start < 0:
        raise SourceError("arm: results container not found — the careers page layout changed")
    end = html.find("data-save-jobs", start)
    region = html[start : end if end > start else None]

    jobs, seen = [], set()
    for m in _CARD.finditer(region):
        tag, title = m.group(0), html_to_text(m.group(1))
        href_m = _HREF.search(tag)
        if not href_m or not title:
            continue
        href = href_m.group(1)
        if not href.startswith("/job/") or href in seen:  # skip story/content links
            continue
        seen.add(href)
        # href = /job/{city}/{slug}/{orgId}/{jobId}
        parts = href.strip("/").split("/")
        city = parts[1].replace("-", " ").title() if len(parts) > 1 else ""
        jobs.append(
            Job(
                company=cfg["name"],
                title=title,
                url=href if href.startswith("http") else BASE + href,
                location=f"{city}, Israel" if city else "Israel",
                source="arm",
            )
        )
    return jobs
