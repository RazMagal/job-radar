"""Comeet (a.k.a. Spark Hire Recruit) public careers API.

Comeet is where most of the Israeli chip scene hosts its jobs (Nuvoton, Ceva,
NextSilicon, proteanTecs, Quantum Machines, ...). Unlike the other ATSes here, its
public API is keyed by a per-company `uid` AND a `token`, both of which are baked into
the company's Comeet-hosted careers page — harvest them once and store them in the
config (see the header of config/companies.yaml for how). The token is per-company and
stable, so it's safe to hardcode; there's no other auth and no rate limiting.

The list response carries no job description (the `details` field is always null, even
on the per-position endpoint), so there's no describer — Comeet jobs are matched on
title only, and `scan --deep` keeps the role->CV mapping for them.
"""

from __future__ import annotations

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import SourceError, parse_json, register, require

API = "https://www.comeet.co/careers-api/2.0/company/{uid}/positions"


@register("comeet")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    # deep is a no-op: Comeet's API exposes no description to fetch.
    uid, token = require(cfg, "uid", "token")
    r = SESSION.get(API.format(uid=uid), params={"token": token}, timeout=TIMEOUT)
    if r.status_code == 400:
        # bad/rotated token, or the account was deactivated (both come back as 400)
        raise SourceError(
            f"comeet board {uid!r} returned 400 — wrong token or the account is "
            "deactivated (re-harvest the uid/token from the Comeet-hosted page)"
        )
    r.raise_for_status()

    payload = parse_json(r, f"comeet/{uid}")
    if not isinstance(payload, list):
        # the error shape is a dict: {"status":400,"message":"..."}
        msg = payload.get("message") if isinstance(payload, dict) else "unexpected response"
        raise SourceError(f"comeet board {uid!r}: {msg}")

    jobs = []
    for j in payload:
        loc = j.get("location") or {}
        where = loc.get("name") or ", ".join(
            x for x in (loc.get("city"), loc.get("country")) if x
        )
        jobs.append(
            Job(
                company=cfg["name"],
                title=j.get("name", ""),
                url=j.get("url_comeet_hosted_page", "") or j.get("url_active_page", ""),
                location=where,
                department=j.get("department") or "",
                posted_at=(j.get("time_updated") or "")[:10],
                source="comeet",
            )
        )
    return jobs
