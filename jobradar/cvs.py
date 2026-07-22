"""Which CV to send for which role — deterministic role -> CV mapping (Stage 1).

The tool only *names* the CV to send; it never stores, reads, or ships the file. The
actual PDFs/DOCX live in cv/ (gitignored) — personal data that must not reach the public
repo or the published page. Only the mapping in config/cvs.yaml (labels + filenames) is
tracked, and only the label is ever put on the page.

Stage 2 (per-job choice from the job description) is in ROADMAP.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class CV:
    label: str
    file: str = ""
    roles: list[str] = field(default_factory=list)


@dataclass
class CVRegistry:
    cvs: list[CV] = field(default_factory=list)
    by_role: dict[str, CV] = field(default_factory=dict)
    # roles listed on more than one CV; the first wins, but worth flagging.
    conflicts: dict[str, list[str]] = field(default_factory=dict)

    def for_role(self, role_id: str) -> CV | None:
        return self.by_role.get(role_id)


def load_cvs(path) -> CVRegistry:
    """Absent or empty file is fine — the feature just stays dormant (no CV labels)."""
    p = Path(path)
    if not p.exists():
        return CVRegistry()

    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    cvs: list[CV] = []
    by_role: dict[str, CV] = {}
    conflicts: dict[str, list[str]] = {}

    for c in raw.get("cvs") or []:
        if not c.get("label"):
            raise ValueError(f"{p}: every CV needs a 'label': {c!r}")
        cv = CV(label=c["label"], file=c.get("file", "") or "", roles=list(c.get("roles") or []))
        cvs.append(cv)
        for role_id in cv.roles:
            if role_id in by_role:
                conflicts.setdefault(role_id, [by_role[role_id].label]).append(cv.label)
            else:
                by_role[role_id] = cv  # first CV listed for a role wins

    return CVRegistry(cvs=cvs, by_role=by_role, conflicts=conflicts)
