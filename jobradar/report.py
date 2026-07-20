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
        # </script> inside JSON data would close the tag early and break the page.
        payload = json.dumps(value, ensure_ascii=False).replace("</", "<\\/")
        html = html.replace(token, payload)
    return html


def write_html(path: Path, jobs: list[dict], meta: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(jobs, meta), encoding="utf-8")
    return path


def render_markdown(jobs: list[dict], meta: dict, limit: int = 40) -> str:
    lines = [
        "## job-radar",
        "",
        f"{meta['new_count']} new match(es) out of {len(jobs)} shown "
        f"({meta['total_scanned']} scanned across {meta['companies']} boards).",
        "",
    ]

    if meta.get("errors"):
        lines += ["### Board errors", ""]
        lines += [f"- **{e['company']}** — {e['error']}" for e in meta["errors"]]
        lines += [""]

    new_jobs = [j for j in jobs if j.get("is_new")]
    if not new_jobs:
        lines += ["_No new postings this run._"]
        return "\n".join(lines)

    by_role: dict[str, list[dict]] = {}
    for j in new_jobs:
        by_role.setdefault(j.get("role_label") or "Other", []).append(j)

    for role, group in by_role.items():
        lines += [f"### {role} ({len(group)})", ""]
        for j in group[:limit]:
            where = f" — {j['location']}" if j.get("location") else ""
            lines.append(f"- [{j['title']}]({j['url']}) · {j['company']}{where}")
        if len(group) > limit:
            lines.append(f"- _...and {len(group) - limit} more_")
        lines.append("")

    return "\n".join(lines)


def build_meta(total_scanned: int, new_count: int, companies: int, errors: list[dict]) -> dict:
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "total_scanned": total_scanned,
        "new_count": new_count,
        "companies": companies,
        "errors": errors,
    }


def to_payload(job: Job, is_new: bool, applied: bool) -> dict:
    d = job.to_dict()
    d["is_new"] = is_new
    d["applied"] = applied
    return d
