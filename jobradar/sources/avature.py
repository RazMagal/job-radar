"""Avature careers portal — HTML only, no public JSON.

Avature (e.g. synopsys.avature.net) server-renders its search results, so this parses the
JobDetail anchors out of the location-filtered results page. Config:
  host    the Avature host (e.g. synopsys.avature.net)
  filter  the raw query string that pins the country facet (portal-specific — read it off
          the site's location filter, e.g. "2001=21374&2001_format=3135&listFilterMode=1"
          where 21374 = Israel on the Synopsys portal)
Location isn't shown on the card, but the facet already restricts to the target country,
so it's recorded as that country. Kept isolated: bad markup fails this board only.
"""

from __future__ import annotations

import re

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import html_to_text, register, require

RESULTS = "https://{host}/careers/SearchJobs/"
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
PAGE = 100
MAX_PAGES = 10

_ANCHOR = re.compile(
    r'<a\b[^>]*href="([^"]*/careers/JobDetail/[^"]+)"[^>]*>(.*?)</a>', re.S
)


@register("avature")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    (host,) = require(cfg, "host")
    filt = cfg.get("filter", "")
    country = cfg.get("country", "Israel")

    jobs, seen = [], set()
    offset = 0
    for _ in range(MAX_PAGES):
        query = f"{filt}&jobRecordsPerPage={PAGE}&jobOffset={offset}" if filt else \
                f"jobRecordsPerPage={PAGE}&jobOffset={offset}"
        r = SESSION.get(
            RESULTS.format(host=host) + "?" + query,
            headers={"User-Agent": BROWSER_UA},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        found = 0
        for m in _ANCHOR.finditer(r.text):
            href, title = m.group(1), html_to_text(m.group(2))
            if not title or href in seen:
                continue
            seen.add(href)
            found += 1
            jobs.append(
                Job(
                    company=cfg["name"],
                    title=title,
                    url=href,
                    location=country,
                    source="avature",
                )
            )
        # the portal caps a page well below jobRecordsPerPage, so advance jobOffset by the
        # number actually parsed; stop when a page adds nothing new.
        if found == 0:
            break
        offset += found
    return jobs
