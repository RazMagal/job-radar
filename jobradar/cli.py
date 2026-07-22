"""Command line entry point."""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
from pathlib import Path

import yaml

from . import sources
from .cvs import load_cvs
from .matcher import load_roles, match_all
from .models import Job
from .report import build_meta, render_markdown, to_payload, write_html
from .store import Store

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config"
DEFAULT_DATA = ROOT / "data"
DEFAULT_OUT = ROOT / "site" / "index.html"

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def _color(enabled: bool):
    if enabled:
        return GREEN, RED, YELLOW, DIM, RESET
    return "", "", "", "", ""


def load_companies(path: Path, ci: bool = False) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    entries = []
    for c in raw.get("companies") or []:
        if not c.get("enabled", True):
            continue
        if ci and not c.get("ci", True):
            continue
        if not c.get("name") or not c.get("type"):
            raise SystemExit(f"{path}: every company needs a 'name' and a 'type': {c!r}")
        entries.append(c)
    if not entries:
        raise SystemExit(f"{path}: no enabled companies to scan")
    return entries


def fetch_all(companies: list[dict], workers: int = 8) -> tuple[list[Job], list[dict]]:
    """Fetch every board in parallel. One bad board must never abort the run."""
    jobs: list[Job] = []
    errors: list[dict] = []

    def run(cfg: dict) -> list[Job]:
        return list(sources.get(cfg["type"])(cfg))

    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run, c): c for c in companies}
        for fut in cf.as_completed(futures):
            cfg = futures[fut]
            try:
                jobs.extend(fut.result())
            except Exception as exc:
                errors.append({"company": cfg["name"], "error": str(exc)})

    return jobs, errors


# --------------------------------------------------------------------------- scan


def cmd_scan(args) -> int:
    g, r, _y, dim, reset = _color(sys.stdout.isatty())
    config_dir = Path(args.config)

    settings, profiles = load_roles(config_dir / "roles.yaml")
    companies = load_companies(config_dir / "companies.yaml", ci=args.ci)

    print(f"Scanning {len(companies)} board(s)...")
    raw_jobs, errors = fetch_all(companies)
    matches = match_all(raw_jobs, settings, profiles)

    # De-duplicate: the same posting can arrive from several sources.
    unique: dict[str, Job] = {}
    for job in matches:
        unique.setdefault(job.id, job)
    matches = list(unique.values())

    # Tag each job with the CV to send for its role (label only — never the file).
    cvs = load_cvs(config_dir / "cvs.yaml")
    for job in matches:
        cv = cvs.for_role(job.role)
        if cv:
            job.cv_label = cv.label

    # The scan is stateless: it renders the current matches and nothing personal. "New"
    # and "applied" are tracked per-device in the browser (see template.html), so no seen
    # log, no applied state, and nothing to keep private ever reaches this output.
    payload = [to_payload(j) for j in matches]
    meta = build_meta(len(raw_jobs), len(companies), errors)

    out = write_html(Path(args.out), payload, meta)
    data_dir = Path(args.data)
    data_dir.mkdir(parents=True, exist_ok=True)
    # latest.json is the local catalog `applied <id>` resolves metadata from; gitignored.
    (data_dir / "latest.json").write_text(
        json.dumps({"meta": meta, "jobs": payload}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    for err in errors:
        print(f"  {r}FAIL{reset} {err['company']}: {err['error']}", file=sys.stderr)

    print(
        f"{g}{len(matches)} match(es){reset} · {len(raw_jobs)} scanned · "
        f"{len(errors)} board error(s)"
    )
    print(f"{dim}report: {out}{reset}")

    if args.markdown:
        Path(args.markdown).write_text(render_markdown(payload, meta), encoding="utf-8")

    if args.print:
        for j in matches:
            cv = f"  [{j.cv_label}]" if j.cv_label else ""
            print(f"  [{j.score:>2}] {j.company}: {j.title} — {j.location}{cv}\n       {j.url}")

    # Every board failing means something systemic (network, blocked IP) — fail the run.
    return 1 if errors and len(errors) == len(companies) else 0


# -------------------------------------------------------------------------- check


def cmd_check(args) -> int:
    g, r, _y, dim, reset = _color(sys.stdout.isatty())
    companies = load_companies(Path(args.config) / "companies.yaml")

    print(f"Checking {len(companies)} board(s)...\n")
    failures = 0
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(lambda c: list(sources.get(c["type"])(c)), c): c for c in companies}
        for fut in cf.as_completed(futures):
            cfg = futures[fut]
            label = f"{cfg['name']} ({cfg['type']})"
            try:
                found = fut.result()
            except Exception as exc:
                failures += 1
                print(f"  {r}FAIL{reset} {label}: {exc}")
            else:
                mark = f"{g}OK{reset}" if found else f"{r}EMPTY{reset}"
                print(f"  {mark}   {label}: {len(found)} posting(s)")

    print(f"\n{dim}{len(companies) - failures}/{len(companies)} board(s) reachable{reset}")
    return 1 if failures else 0


# ------------------------------------------------------------------------ applied


def cmd_applied(args) -> int:
    store = Store(Path(args.data))
    rc = 0
    for needle in args.ids:
        found = store.lookup(needle)
        if not found:
            print(f"unknown job: {needle} (run a scan first, or pass the job URL)", file=sys.stderr)
            rc = 1
            continue
        job_id, meta = found
        entry = store.mark_applied(job_id, meta, note=args.note, cv=args.cv)
        cv = f"  (cv: {entry['cv']})" if entry.get("cv") else ""
        print(f"applied {job_id}  {entry['company']}: {entry['title']}{cv}")
    return rc


def cmd_unapplied(args) -> int:
    store = Store(Path(args.data))
    rc = 0
    for needle in args.ids:
        found = store.lookup(needle)
        job_id = found[0] if found else needle
        if store.unmark_applied(job_id):
            print(f"un-applied {job_id}")
        else:
            print(f"not in the applied log: {needle}", file=sys.stderr)
            rc = 1
    return rc


def cmd_log(args) -> int:
    store = Store(Path(args.data))
    if not store.applied:
        print("Nothing applied yet.")
        return 0
    rows = sorted(store.applied.items(), key=lambda kv: kv[1].get("applied_on", ""), reverse=True)
    print(f"{len(rows)} application(s):\n")
    for job_id, meta in rows:
        print(f"  {meta.get('applied_on', '?')}  {job_id}  {meta.get('company', '')}: {meta.get('title', '')}")
        if meta.get("cv"):
            print(f"              cv:   {meta['cv']}")
        if meta.get("note"):
            print(f"              note: {meta['note']}")
        if meta.get("url"):
            print(f"              {meta['url']}")
    return 0


# ---------------------------------------------------------------------------- cv


def cmd_cv(args) -> int:
    config_dir = Path(args.config)
    reg = load_cvs(config_dir / "cvs.yaml")
    if not reg.cvs:
        print("No CVs configured. Add them to config/cvs.yaml (see cv/README.md).")
        return 0

    _settings, profiles = load_roles(config_dir / "roles.yaml")
    cv_dir = config_dir.parent / "cv"

    print(f"{len(reg.cvs)} CV(s):\n")
    for cv in reg.cvs:
        roles = ", ".join(cv.roles) or "-"
        if not cv.file:
            state = "no file"
        elif (cv_dir / cv.file).exists():
            state = "ok"
        else:
            state = "MISSING"
        print(f"  {cv.label:14} roles: {roles:26} file: {cv.file or '-':20} [{state}]")

    uncovered = sorted({p.id for p in profiles} - set(reg.by_role))
    if uncovered:
        print(f"\nroles with no CV: {', '.join(uncovered)}")
    for role_id, labels in reg.conflicts.items():
        print(f"role {role_id!r} is claimed by several CVs ({', '.join(labels)}); first wins")
    return 0


# --------------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jobradar", description="Scan company job boards for roles you want.")
    p.add_argument("--config", default=str(DEFAULT_CONFIG), help="config directory")
    p.add_argument("--data", default=str(DEFAULT_DATA), help="data directory (local applied log + last scan)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="fetch every board, match, and write the report")
    s.add_argument("--out", default=str(DEFAULT_OUT), help="HTML report path")
    s.add_argument("--markdown", help="also write a markdown digest here")
    s.add_argument("--ci", action="store_true", help="skip boards marked `ci: false`")
    s.add_argument("--print", action="store_true", help="print matches to stdout")
    s.set_defaults(func=cmd_scan)

    c = sub.add_parser("check", help="verify every configured board still resolves")
    c.set_defaults(func=cmd_check)

    a = sub.add_parser("applied", help="mark job id(s) or URL(s) as applied")
    a.add_argument("ids", nargs="+")
    a.add_argument("--note", default="", help="free-text note")
    a.add_argument("--cv", default="", help="which CV you sent (label from cvs.yaml)")
    a.set_defaults(func=cmd_applied)

    u = sub.add_parser("unapplied", help="undo an `applied` mark")
    u.add_argument("ids", nargs="+")
    u.set_defaults(func=cmd_unapplied)

    lg = sub.add_parser("log", help="show everything you've applied to")
    lg.set_defaults(func=cmd_log)

    cv = sub.add_parser("cv", help="manage CVs (which one to send per role)")
    cvsub = cv.add_subparsers(dest="cv_command", required=True)
    cvl = cvsub.add_parser("list", help="list configured CVs and their role coverage")
    cvl.set_defaults(func=cmd_cv)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
