"""Optional LinkedIn / Indeed / Glassdoor coverage via the `python-jobspy` package.

Kept optional on purpose:
  * it's an extra dependency (`pip install -r requirements-jobspy.txt`),
  * these boards rate-limit and largely block datacenter IPs, so this source is
    unreliable from GitHub Actions — run it locally.

Mark a company entry `ci: false` in companies.yaml to skip it in Actions.
"""

from __future__ import annotations

from ..models import Job
from .base import SourceError, register


@register("jobspy")
def fetch(cfg: dict) -> list[Job]:
    try:
        from jobspy import scrape_jobs
    except ImportError:
        raise SourceError(
            "jobspy source requires: pip install -r requirements-jobspy.txt"
        ) from None

    try:
        df = scrape_jobs(
            site_name=cfg.get("sites") or ["linkedin", "indeed"],
            search_term=cfg.get("search_term", "verification engineer"),
            location=cfg.get("location", "Israel"),
            country_indeed=cfg.get("country", "israel"),
            results_wanted=int(cfg.get("results", 50)),
            hours_old=int(cfg.get("hours_old", 24 * 14)),
            linkedin_fetch_description=False,
        )
    except Exception as exc:  # scrapers rot; never let one kill the whole run
        raise SourceError(f"jobspy scrape failed: {exc}") from exc

    jobs = []
    for row in df.to_dict("records"):
        posted = row.get("date_posted")
        jobs.append(
            Job(
                company=str(row.get("company") or cfg["name"]),
                title=str(row.get("title") or ""),
                url=str(row.get("job_url") or ""),
                location=str(row.get("location") or ""),
                posted_at=str(posted)[:10] if posted else "",
                source=f"jobspy:{row.get('site', '')}",
            )
        )
    return jobs
