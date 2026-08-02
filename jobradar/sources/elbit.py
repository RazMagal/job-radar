"""Elbit Systems' own careers backend.

Elbit (Israel's largest private defense electronics house — radar, EW, C4I, avionics)
isn't on a third-party ATS. Its careers site elbitsystemscareer.com is a Next.js app that
hydrates from one static JSON blob:

    https://elbitsystemscareer.com/cron/jobs.json

~680 open reqs, each with the full description (so `scan --deep` gets RF/DSP/FPGA/
verification roles whose *title* is generic). Every posting on this portal is an Israel
role, so we tag it Israel — the JSON's own `area` field is an Israeli region (North,
Center, Sharon, Shfela, South, Haifa, Jerusalem), which we keep as context. The detail
page is /job/?jid={jobId} (discovered by clicking a card — there's no slug in the JSON).

No token, no pagination, no auth; the scanner's default UA is accepted.
"""

from __future__ import annotations

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import SourceError, html_to_text, parse_json, register

API = "https://elbitsystemscareer.com/cron/jobs.json"
JOB_URL = "https://elbitsystemscareer.com/job/?jid={jid}"

# The `area` field is a coarse Israeli region — but it also carries the odd system
# artifact ("DataMigration", "Nationwide deployment"). Only surface it as context when
# it's a real region; otherwise fall back to plain "Israel".
_REGIONS = {"north", "center", "sharon", "shfela", "south", "haifa", "jerusalem", "jerusalem area"}


def _location(job: dict) -> str:
    """Every req on this portal is in Israel; keep the region as context so the report
    shows North/Center/... The trailing ", Israel" is what satisfies the location filter."""
    area = " ".join((job.get("area") or "").split())  # collapse stray \r\n
    return f"{area}, Israel" if area.lower() in _REGIONS else "Israel"


@register("elbit")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    r = SESSION.get(API, timeout=TIMEOUT)
    r.raise_for_status()
    payload = parse_json(r, "elbit")
    if not isinstance(payload, list):
        raise SourceError("elbit: expected a JSON array of jobs (site layout changed?)")

    jobs: list[Job] = []
    for j in payload:
        if j.get("status") != 1:  # 1 == open
            continue
        jid = j.get("jobId")
        if jid is None:
            continue
        desc = ""
        if deep:
            # description/requirements/skills are entity-encoded HTML; html_to_text
            # unescapes twice, which is exactly what this double-encoded blob needs.
            desc = html_to_text(
                " ".join(filter(None, (j.get("description"), j.get("requirements"), j.get("skills"))))
            )
        jobs.append(
            Job(
                company=cfg["name"],
                title=(j.get("jobTitle") or "").strip(),
                url=JOB_URL.format(jid=jid),
                location=_location(j),
                department=(j.get("employerName") or "").strip(),
                posted_at=(j.get("openDate") or j.get("updateDate") or "")[:10],
                source="elbit",
                description=desc,
            )
        )
    return jobs
