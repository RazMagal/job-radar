"""Israel Aerospace Industries (IAI) — and its Elta subsidiary — careers.

IAI's careers site (jobs.iai.co.il) is WordPress behind a Reblaze WAF: the *page*
navigation gets a JS challenge, but the jobs load from one static asset the WAF does
**not** gate, so a plain GET returns the whole feed:

    https://jobs.iai.co.il/wp-content/themes/tyco-wp/assets/json/jobs.json

~470 reqs, each with a full description, so `scan --deep` works. Content is **Hebrew** —
titles/descriptions/cities — with Latin acronyms (RF/FPGA/DSP/VLSI) kept inline; the
English role keywords catch those, the Hebrew keywords in roles.yaml catch the rest. Every
posting is an Israel role. Detail page is /job/{id}; Elta reqs land in this same feed.

Fields are 2-letter keys: tl=title, dc=description (plain text), ct=city, tp=employment
type, jc=job category. Titles carry a trailing "[123456]" code and stray NBSPs — cleaned.
"""

from __future__ import annotations

import re

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import SourceError, html_to_text, parse_json, register

API = "https://jobs.iai.co.il/wp-content/themes/tyco-wp/assets/json/jobs.json"
JOB_URL = "https://jobs.iai.co.il/job/{id}"
_CODE_SUFFIX = re.compile(r"\s*\[\d+\]\s*$")  # titles end with a bracketed public code


def _title(raw: str) -> str:
    return _CODE_SUFFIX.sub("", (raw or "").replace("\xa0", " ")).strip()


@register("iai")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    r = SESSION.get(API, timeout=TIMEOUT)
    r.raise_for_status()
    payload = parse_json(r, "iai")
    if not isinstance(payload, list):
        raise SourceError("iai: expected a JSON array of jobs (site layout changed?)")

    jobs: list[Job] = []
    for j in payload:
        jid = j.get("id")
        if jid is None:
            continue
        city = (j.get("ct") or "").strip()
        jobs.append(
            Job(
                company=cfg["name"],
                title=_title(j.get("tl")),
                url=JOB_URL.format(id=jid),
                # Every posting is in Israel; keep the (Hebrew) city as context, and the
                # trailing ", Israel" is what satisfies the location filter.
                location=f"{city}, Israel" if city else "Israel",
                department=(j.get("jc") or "").strip(),
                posted_at="",  # the feed carries no post date
                source="iai",
                description=html_to_text(j.get("dc", "")) if deep else "",
            )
        )
    return jobs
