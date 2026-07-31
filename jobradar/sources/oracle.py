"""Oracle Recruiting Cloud (ORC) public job-requisitions API.

Texas Instruments — and many other large employers — run Oracle ORC. The public
`recruitingCEJobRequisitions` resource takes a `finder` expression that filters by site
and location server-side, so a plain GET returns just the Israel reqs. No auth.

Config: `host` (the fa.oraclecloud.com host — careers.<co>.com usually proxies/redirects
to it), `site` (siteNumber, e.g. CX), `location_id` (the Israel GeographyId facet), and an
optional `job_url` template ({id}) for the public posting link. Derive them by loading the
company's careers page and watching the hcmRestApi XHR. The list carries the description,
so `scan --deep` works.
"""

from __future__ import annotations

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import html_to_text, parse_json, register, require

RESOURCE = "https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
PAGE = 200
MAX_PAGES = 10


@register("oracle")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    host, site = require(cfg, "host", "site")
    location_id = cfg.get("location_id", "")
    job_url = cfg.get("job_url") or (
        f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{{id}}"
    )

    jobs: list[Job] = []
    offset = 0
    for _ in range(MAX_PAGES):
        finder = f"findReqs;siteNumber={site}"
        if location_id:
            finder += f",selectedLocationsFacet={location_id}"
        finder += f",limit={PAGE},offset={offset}"
        params = {
            "onlyData": "true",
            "expand": "requisitionList.secondaryLocations",
            "finder": finder,
        }
        r = SESSION.get(RESOURCE.format(host=host), params=params, timeout=TIMEOUT)
        r.raise_for_status()
        block = (parse_json(r, f"oracle/{site}").get("items") or [{}])[0]
        reqs = block.get("requisitionList") or []
        if not reqs:
            break
        for req in reqs:
            description = ""
            if deep:
                description = html_to_text(
                    " ".join(
                        x
                        for x in (
                            req.get("ShortDescriptionStr"),
                            req.get("ExternalResponsibilitiesStr"),
                            req.get("ExternalQualificationsStr"),
                        )
                        if x
                    )
                )
            jobs.append(
                Job(
                    company=cfg["name"],
                    title=req.get("Title", ""),
                    url=job_url.format(id=req.get("Id", "")),
                    location=req.get("PrimaryLocation", "") or "",
                    posted_at=(req.get("PostedDate") or "")[:10],
                    source="oracle",
                    description=description,
                )
            )
        offset += len(reqs)
        if offset >= (block.get("TotalJobsCount") or 0):
            break
    return jobs
