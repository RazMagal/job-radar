"""Renders the scan results as a static page (and a markdown digest for CI summaries)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import Job

TEMPLATE = Path(__file__).with_name("template.html")


def render_html(jobs: list[dict], meta: dict) -> str:
    html = TEMPLATE.read_text(encoding="utf-8")
    for token, value in (("__JOBS_JSON__", jobs), ("__META_JSON__", meta)):
        if token not in html:
            raise RuntimeError(f"{TEMPLATE} is missing the {token} placeholder")
        # Titles come from third-party boards: escape every "<" so neither "</script>"
        # nor the "<!--<script" double-escaped-state trick can break out of the inline
        # block. U+2028/9 are legal in JSON strings but terminate a JS line.
        payload = (
            json.dumps(value, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029")
        )
        html = html.replace(token, payload)
    return html


def write_html(path: Path, jobs: list[dict], meta: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(jobs, meta), encoding="utf-8")
    return path


def render_markdown(jobs: list[dict], meta: dict, limit: int = 25) -> str:
    lines = [
        "## job-radar",
        "",
        f"{len(jobs)} match(es) across {meta['companies']} boards "
        f"({meta['total_scanned']} postings scanned).",
        "",
    ]

    if meta.get("errors"):
        lines += ["### Board errors", ""]
        lines += [f"- **{e['company']}** — {e['error']}" for e in meta["errors"]]
        lines += [""]

    if not jobs:
        lines += ["_No matches this run._"]
        return "\n".join(lines)

    # "new" is per-device (browser-side), so the digest just lists everything by role.
    by_role: dict[str, list[dict]] = {}
    for j in jobs:
        by_role.setdefault(j.get("role_label") or "Other", []).append(j)

    for role, group in by_role.items():
        lines += [f"### {role} ({len(group)})", ""]
        for j in group[:limit]:
            where = f" — {j['location']}" if j.get("location") else ""
            cv = f" · **send:** {j['cv']}" if j.get("cv") else ""
            why = f" _({j['cv_reason']})_" if j.get("cv_reason") else ""
            lines.append(f"- [{j['title']}]({j['url']}) · {j['company']}{where}{cv}{why}")
        if len(group) > limit:
            lines.append(f"- _...and {len(group) - limit} more_")
        lines.append("")

    return "\n".join(lines)


def build_meta(total_scanned: int, companies: int, errors: list[dict]) -> dict:
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "total_scanned": total_scanned,
        "companies": companies,
        "errors": errors,
    }


def to_payload(job: Job) -> dict:
    d = job.to_dict()
    # The description is transient --deep working data: large, and it has no business
    # in a published page or the local catalog.
    d.pop("description", None)
    d["cv"] = d.pop("cv_label", "")  # the page reads `cv`; never the file, only the label
    return d
