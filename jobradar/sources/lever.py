"""Lever public postings API."""

from __future__ import annotations

from datetime import datetime, timezone

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import SourceError, html_to_text, parse_json, register, require

API = "https://api{region}.lever.co/v0/postings/{board}?mode=json"

# Lever runs a separate EU data region. Boards hosted there 404 on the US endpoint,
# which looks identical to a wrong token — set `region: eu` for those (e.g. Mobileye).
REGIONS = {"": "", "us": "", "eu": ".eu"}


def _date(ms) -> str:
    if not ms:
        return ""
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _description(j: dict) -> str:
    """The full posting is split: descriptionPlain (intro) + lists[] (the actual
    responsibilities/requirements, as HTML) + additionalPlain (closing)."""
    parts = [j.get("descriptionPlain", "") or ""]
    for section in j.get("lists") or []:
        parts.append(section.get("text", "") or "")
        parts.append(html_to_text(section.get("content", "") or ""))
    parts.append(j.get("additionalPlain", "") or "")
    return "\n".join(p for p in parts if p).strip()


@register("lever")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    (board,) = require(cfg, "board")
    region = str(cfg.get("region", "")).lower()
    if region not in REGIONS:
        raise SourceError(f"unknown lever region {region!r} (use one of: {sorted(REGIONS)})")

    r = SESSION.get(API.format(region=REGIONS[region], board=board), timeout=TIMEOUT)
    if r.status_code == 404:
        raise SourceError(
            f"lever board {board!r} does not exist in the "
            f"{region or 'us'} region (try `region: eu`)"
        )
    r.raise_for_status()

    jobs = []
    for j in parse_json(r, f"lever/{board}"):
        cats = j.get("categories") or {}
        jobs.append(
            Job(
                company=cfg["name"],
                title=j.get("text", ""),
                url=j.get("hostedUrl", "") or j.get("applyUrl", ""),
                location=cats.get("location", "") or "",
                department=cats.get("team", "") or "",
                posted_at=_date(j.get("createdAt")),
                source="lever",
                description=_description(j) if deep else "",
            )
        )
    return jobs
