"""Scores each posting against your role profiles.

By default matching is title-only and deliberately dumb-but-predictable: ATS list
endpoints don't return descriptions, and a keyword in the title is the strongest signal.
Under ``scan --deep`` the job description is also scanned (see ``score``), which catches
postings whose title hides the role — a "VLSI Engineer" or "Systems Engineer" that is
really chip design or verification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import yaml

from .models import Job, normalize

TITLE_HIT = 3  # a primary keyword in the title
BOOST_HIT = 1  # a supporting keyword ("uvm", "asic", ...)
DESC_HIT = 2  # a primary keyword found in the body but not the title (--deep only)
DESC_MIN_HITS = 2  # ...and the body must carry at least this many distinct ones to count


# Keyword matching is not plain substring. Inclusion keywords anchor at a word START
# only — "soc" can't hit "as-soc-iate" and "asic" can't hit "basic", while "rf" still
# hits "RFIC" and "soc" still hits "soc validation". Exclusion keywords anchor on BOTH
# sides: they delete jobs, so they must be exact words/phrases — "intern" must not
# swallow "International" (variants like "internship" are listed explicitly in
# roles.yaml). Hebrew keywords keep plain substring matching: the prepositions ו/ב/ל
# glue onto the front of the word, so a left anchor would miss "ואימות".


@lru_cache(maxsize=None)
def _include_pat(kw: str) -> re.Pattern | None:
    return re.compile(r"\b" + re.escape(kw)) if kw.isascii() else None


@lru_cache(maxsize=None)
def _exclude_pat(kw: str) -> re.Pattern | None:
    return re.compile(r"\b" + re.escape(kw) + r"\b") if kw.isascii() else None


def _hit(kw: str, text: str) -> bool:
    pat = _include_pat(kw)
    return pat.search(text) is not None if pat else kw in text


def _excluded(text: str, keywords: list[str]) -> bool:
    for kw in keywords:
        pat = _exclude_pat(kw)
        if pat.search(text) is not None if pat else kw in text:
            return True
    return False


def _distinct(keywords: list[str]) -> list[str]:
    """Drop any keyword that is a substring of another matched one, so overlapping
    phrases ("verification" vs "design verification") count as one signal, not two."""
    return [kw for kw in keywords if not any(kw != other and kw in other for other in keywords)]


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


def score(
    job: Job, settings: Settings, profiles: list[Profile], use_description: bool = False
) -> Job | None:
    """Return the job annotated with its best-matching profile, or None if it's out.

    Two passes. The title pass is authoritative and unchanged from a plain scan: a job
    the title already classifies keeps that role. Only if the title classifies it into
    *nothing* does the ``--deep`` body pass run — so the description can pull in a
    posting the title hid ("VLSI Engineer", "Member of Technical Staff") but can never
    *re-bucket* one the title already placed (a chip role whose blurb name-drops ML must
    stay chip). The body pass needs a clear signal — ``DESC_MIN_HITS`` distinct,
    non-overlapping primary keywords, none of them excluded — so a stray mention in a
    long description can't drag an unrelated job in. Body-sourced hits are prefixed "~"
    in ``job.matched``. Only sources whose listing returns descriptions benefit
    (greenhouse/ashby/lever/jobspy); Workday stays title-only.
    """
    title = normalize(job.title)

    if _excluded(title, settings.exclude_titles):
        return None
    if not _location_ok(job, settings):
        return None

    # --- pass 1: title only (the whole story for a plain scan) ---------------------
    best: tuple[int, list[str], Profile] | None = None
    for prof in profiles:
        if _excluded(title, prof.exclude):
            continue
        hits = [kw for kw in prof.match_any if _hit(kw, title)]
        if not hits:
            continue
        boosts = [kw for kw in prof.boost if _hit(kw, title)]
        total = len(hits) * TITLE_HIT + len(boosts) * BOOST_HIT
        if best is None or total > best[0]:
            best = (total, hits + boosts, prof)
    if best is not None and best[0] >= settings.min_score:
        total, matched, prof = best
        job.role, job.role_label, job.score, job.matched = prof.id, prof.label, total, matched
        return job

    # --- pass 2: body fallback for a title the pass above left unclassified --------
    if not (use_description and job.description):
        return None
    desc = normalize(job.description)
    best = None
    for prof in profiles:
        if _excluded(title, prof.exclude) or _excluded(desc, prof.exclude):
            continue
        title_hits = [kw for kw in prof.match_any if _hit(kw, title)]
        body = _distinct([kw for kw in prof.match_any if _hit(kw, desc) and kw not in title_hits])
        if len(body) < DESC_MIN_HITS:
            continue
        boosts = [kw for kw in prof.boost if _hit(kw, title)]
        total = len(title_hits) * TITLE_HIT + len(boosts) * BOOST_HIT + len(body) * DESC_HIT
        matched = title_hits + boosts + [f"~{kw}" for kw in body]
        if best is None or total > best[0]:
            best = (total, matched, prof)
    if best is not None and best[0] >= settings.min_score:
        total, matched, prof = best
        job.role, job.role_label, job.score, job.matched = prof.id, prof.label, total, matched
        return job
    return None


def match_all(
    jobs, settings: Settings, profiles: list[Profile], use_description: bool = False
) -> list[Job]:
    out = [m for j in jobs if (m := score(j, settings, profiles, use_description))]
    # Two stable passes: newest first within a score, highest score first overall.
    # ISO dates sort correctly as strings — and a source that one day emits a
    # non-ISO date must not crash the whole scan over a sort key.
    out.sort(key=lambda j: j.posted_at or "", reverse=True)
    out.sort(key=lambda j: j.score, reverse=True)
    return out
