"""LinkedIn / Indeed coverage via the `python-jobspy` package.

This is the only way to see postings from companies with no reachable ATS — Qualcomm,
Google, AMD, Synopsys, Apple — so it's installed by default. Three caveats:
  * pulls ~120 MB of pandas/numpy, so CI installs requirements-core.txt instead,
  * the package is effectively unmaintained (last publish mid-2025), so it will
    break without warning,
  * LinkedIn is aggressive about datacenter IPs — verified working from a
    residential connection, expect it to return nothing from GitHub Actions.
    Hence `ci: false` on these entries.

Glassdoor is deliberately not supported: jobspy has no Glassdoor domain for Israel
and raises rather than skipping, which would take the whole run down with it.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..models import Job
from .base import SourceError, register

SUPPORTED = {"linkedin", "indeed"}


def _iso(value) -> str:
    """jobspy leaves date_posted null on a fair share of LinkedIn rows (NaT, None, nan)."""
    if value is None:
        return ""
    text = str(value)
    if text.lower() in ("nat", "nan", "none", ""):
        return ""
    return text[:10]


@register("jobspy")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    try:
        from jobspy import scrape_jobs
    except ImportError:
        raise SourceError(
            "jobspy source requires the python-jobspy package: pip install -r requirements.txt "
            "(or drop these entries from companies.yaml if you only want the ATS boards)"
        ) from None

    requested = [s.lower() for s in (cfg.get("sites") or ["indeed", "linkedin"])]
    unsupported = [s for s in requested if s not in SUPPORTED]
    if unsupported:
        raise SourceError(
            f"jobspy sites {unsupported} not supported here (only {sorted(SUPPORTED)}); "
            "glassdoor has no Israel domain and aborts the whole batch"
        )

    hours_old = int(cfg.get("hours_old", 24 * 14))
    cutoff = (date.today() - timedelta(hours=hours_old / 24 if hours_old else 0)).isoformat()

    jobs: list[Job] = []
    failures: list[str] = []

    # One call per site: jobspy has no per-site isolation, so a single site raising
    # inside a combined call throws away the other site's results too.
    for site in requested:
        try:
            df = scrape_jobs(
                site_name=[site],
                search_term=cfg.get("search_term", "verification engineer"),
                location=cfg.get("location", "Israel"),
                country_indeed=cfg.get("country", "israel"),
                results_wanted=int(cfg.get("results", 50)),
                hours_old=hours_old,
                # Under --deep, pull descriptions too (slower — a fetch per LinkedIn row)
                # so CV matching has body text to work with, not just the title.
                linkedin_fetch_description=deep,
            )
        except Exception as exc:
            failures.append(f"{site}: {exc}")
            continue

        rows = df.to_dict("records") if df is not None else []
        if not rows:
            # Distinguishable from "nothing matched": these boards return empty when
            # they block you, which is the expected CI failure mode.
            failures.append(f"{site}: returned no rows (rate-limited or blocked?)")
            continue

        for row in rows:
            posted = _iso(row.get("date_posted"))
            # Indeed does not reliably honour hours_old — it returned rows months
            # outside the window — so re-filter here. Undated rows are kept.
            if posted and posted < cutoff:
                continue
            jobs.append(
                Job(
                    company=str(row.get("company") or cfg["name"]),
                    title=str(row.get("title") or ""),
                    url=str(row.get("job_url") or ""),
                    location=str(row.get("location") or ""),
                    posted_at=posted,
                    source=f"jobspy:{row.get('site', site)}",
                    description=str(row.get("description") or "") if deep else "",
                )
            )

    if failures and not jobs:
        raise SourceError("; ".join(failures))
    return jobs
