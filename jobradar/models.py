"""Core data model: a single job posting."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")
_URL_HOST = re.compile(r"^https?://[^/]*")


def normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace. Used for matching and IDs."""
    return _WS.sub(" ", _PUNCT.sub(" ", (text or "").lower())).strip()


@dataclass
class Job:
    company: str
    title: str
    url: str
    location: str = ""
    department: str = ""
    posted_at: str = ""  # ISO date (YYYY-MM-DD) or ""
    source: str = ""

    # Filled in by the matcher.
    role: str = ""
    role_label: str = ""
    score: int = 0
    matched: list[str] = field(default_factory=list)

    # Filled in from the CV registry: which CV to send for this job (label only).
    cv_label: str = ""
    cv_reason: str = ""  # under --deep: the terms that drove the CV pick

    # Transient: the job description, fetched only under `scan --deep` for CV matching.
    # Never serialised to the payload (see report.to_payload) — it's large and local.
    description: str = ""

    @property
    def id(self) -> str:
        """Stable fingerprint: company|title|location plus the URL *path*, which carries
        the ATS's req id. Without it, several genuinely distinct reqs with the same title
        in the same city hash identically and dedup silently keeps only one (~13% of
        matched jobs, measured). The host is dropped (an ATS region swap shouldn't churn
        ids) and so is the query string (tracking params). The cost: a board that
        re-posts the same req under a fresh id resurfaces it as new — rarer and visible,
        unlike the silent loss."""
        path = _URL_HOST.sub("", (self.url or "").split("?", 1)[0]).rstrip("/")
        key = (
            f"{normalize(self.company)}|{normalize(self.title)}|"
            f"{normalize(self.location)}|{normalize(path)}"
        )
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)
