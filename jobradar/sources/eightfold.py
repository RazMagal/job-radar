"""Eightfold "PCSX" careers API — the platform behind several big-tech careers sites.

Qualcomm and Microsoft both run it: a public JSON search that filters by location
server-side, so a plain GET returns just the Israel roles (Qualcomm — Snapdragon
modem/RF/camera silicon; Microsoft — Azure/security/AI). Same request shape, differing
only by host and tenant `domain`. The search list carries no description, so — like
Workday — each registers a per-job describer that `scan --deep` calls for matched jobs.

Location leakage (Microsoft's `location=Israel` occasionally returns a remote-eligible
foreign role) is left to the roles.yaml location filter, the single place every source is
narrowed to Israel — its `.locations[]` won't contain an Israeli place name, so it drops.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import html_to_text, parse_json, register, register_describer

MAX_PAGES = 15

# config `type` -> (host, tenant domain)
TENANTS = {
    "qualcomm": ("careers.qualcomm.com", "qualcomm.com"),
    "microsoft": ("apply.careers.microsoft.com", "microsoft.com"),
}


def _date(ts) -> str:
    """postedTs / creationTs are Unix epoch seconds."""
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _fetch(name: str, cfg: dict) -> list[Job]:
    host, domain = TENANTS[name]
    location = cfg.get("location", "Israel")
    jobs: list[Job] = []
    offset = 0
    for _ in range(MAX_PAGES):
        # `num` is honoured by Qualcomm but ignored by Microsoft (fixed 10/page), so the
        # loop advances by the count actually returned, never an assumed page size.
        params = {
            "domain": domain,
            "query": "",
            "location": location,
            "start": offset,
            "num": 50,
            "sort_by": "timestamp",
        }
        r = SESSION.get(f"https://{host}/api/pcsx/search", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = parse_json(r, name).get("data") or {}
        positions = data.get("positions") or []
        if not positions:
            break
        for p in positions:
            locs = p.get("locations") or p.get("standardizedLocations") or []
            jobs.append(
                Job(
                    company=cfg["name"],
                    title=p.get("name", ""),
                    # the list returns positionUrl null/relative; the public URL is
                    # /careers/job/{id} on the tenant host for both.
                    url=f"https://{host}/careers/job/{p.get('id', '')}",
                    location=locs[0] if locs else "",
                    department=p.get("department", "") or "",
                    posted_at=_date(p.get("postedTs") or p.get("creationTs")),
                    source=name,
                )
            )
        offset += len(positions)
        if offset >= (data.get("count") or 0):
            break
    return jobs


def _describe(name: str, job: Job) -> str:
    host, domain = TENANTS[name]
    pid = job.url.rstrip("/").split("/")[-1]
    r = SESSION.get(
        f"https://{host}/api/pcsx/position_details",
        params={"position_id": pid, "domain": domain, "hl": "en"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = parse_json(r, f"{name}/detail").get("data") or {}
    return html_to_text(data.get("jobDescription", ""))


@register("qualcomm")
def qualcomm(cfg: dict, deep: bool = False) -> list[Job]:
    return _fetch("qualcomm", cfg)


@register("microsoft")
def microsoft(cfg: dict, deep: bool = False) -> list[Job]:
    return _fetch("microsoft", cfg)


@register_describer("qualcomm")
def _qualcomm_desc(cfg: dict, job: Job) -> str:
    return _describe("qualcomm", job)


@register_describer("microsoft")
def _microsoft_desc(cfg: dict, job: Job) -> str:
    return _describe("microsoft", job)
