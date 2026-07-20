"""Scores each posting against your role profiles.

Matching is title-only and deliberately dumb-but-predictable: ATS list endpoints
don't return descriptions, and fetching every description would mean thousands of
extra requests per scan. A keyword in the title is a far stronger signal anyway.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from .models import Job, normalize

TITLE_HIT = 3  # a primary keyword in the title
BOOST_HIT = 1  # a supporting keyword ("uvm", "asic", ...)


@dataclass
class Profile:
    id: str
    label: str
    match_any: list[str] = field(default_factory=list)
    boost: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


@dataclass
class Settings:
    locations_any: list[str] = field(default_factory=list)
    exclude_titles: list[str] = field(default_factory=list)
    min_score: int = 3


def load_roles(path) -> tuple[Settings, list[Profile]]:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    s = raw.get("settings") or {}
    settings = Settings(
        locations_any=[normalize(x) for x in s.get("locations_any") or []],
        exclude_titles=[normalize(x) for x in s.get("exclude_titles") or []],
        min_score=int(s.get("min_score", 3)),
    )

    profiles = []
    for p in raw.get("profiles") or []:
        profiles.append(
            Profile(
                id=p["id"],
                label=p.get("label", p["id"]),
                match_any=[normalize(x) for x in p.get("match_any") or []],
                boost=[normalize(x) for x in p.get("boost") or []],
                exclude=[normalize(x) for x in p.get("exclude") or []],
            )
        )
    if not profiles:
        raise ValueError(f"{path}: no profiles defined")
    return settings, profiles


def _location_ok(job: Job, settings: Settings) -> bool:
    if not settings.locations_any:
        return True
    loc = normalize(job.location)
    if not loc:
        # No location given: keep it rather than silently dropping a real match.
        return True
    return any(want in loc for want in settings.locations_any)


def score(job: Job, settings: Settings, profiles: list[Profile]) -> Job | None:
    """Return the job annotated with its best-matching profile, or None if it's out."""
    title = normalize(job.title)

    if any(bad in title for bad in settings.exclude_titles):
        return None
    if not _location_ok(job, settings):
        return None

    best: tuple[int, list[str], Profile] | None = None
    for prof in profiles:
        if any(bad in title for bad in prof.exclude):
            continue

        hits = [kw for kw in prof.match_any if kw in title]
        if not hits:
            continue
        boosts = [kw for kw in prof.boost if kw in title]
        total = len(hits) * TITLE_HIT + len(boosts) * BOOST_HIT

        if best is None or total > best[0]:
            best = (total, hits + boosts, prof)

    if best is None or best[0] < settings.min_score:
        return None

    total, matched, prof = best
    job.role, job.role_label, job.score, job.matched = prof.id, prof.label, total, matched
    return job


def match_all(jobs, settings: Settings, profiles: list[Profile]) -> list[Job]:
    out = [m for j in jobs if (m := score(j, settings, profiles))]
    out.sort(key=lambda j: (-j.score, j.posted_at and -int(j.posted_at.replace("-", "")) or 0))
    return out
