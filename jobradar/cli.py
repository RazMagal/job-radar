"""Command line entry point."""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
from pathlib import Path

import yaml

from . import sources
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
    g, r, y, dim, reset = _color(sys.stdout.isatty())
    config_dir = Path(args.config)

    settings, profiles = load_roles(config_dir / "roles.yaml")
    companies = load_companies(config_dir / "companies.yaml", ci=args.ci)
    store = Store(Path(args.data))

    print(f"Scanning {len(companies)} board(s)...")
    raw_jobs, errors = fetch_all(companies)
    matches = match_all(raw_jobs, settings, profiles)

    # De-duplicate: the same posting can arrive from several sources.
    unique: dict[str, Job] = {}
    for job in matches:
        unique.setdefault(job.id, job)
    matches = list(unique.values())

    new_jobs = [j for j in matches if store.is_new(j)]
    if args.new_only:
        matches = new_jobs

    payload = [
        to_payload(j, is_new=store.is_new(j), applied=store.has_applied(j.id)) for j in matches
    ]
    meta = build_meta(len(raw_jobs), len(new_jobs), len(companies), errors)

    out = write_html(Path(args.out), payload, meta)
    Path(args.data, "latest.json").write_text(
        json.dumps({"meta": meta, "jobs": payload}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if not args.dry_run:
        store.record_seen(matches)

    for err in errors:
        print(f"  {r}FAIL{reset} {err['company']}: {err['error']}", file=sys.stderr)

    print(
        f"{g}{len(new_jobs)} new{reset} · {len(matches)} shown · "
        f"{len(raw_jobs)} scanned · {len(errors)} board error(s)"
    )
    print(f"{dim}report: {out}{reset}")

    if args.markdown:
        Path(args.markdown).write_text(render_markdown(payload, meta), encoding="utf-8")

    if args.print_new:
        for j in new_jobs:
            print(f"  [{j.score:>2}] {j.company}: {j.title} — {j.location}\n       {j.url}")

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
        entry = store.mark_applied(job_id, meta, note=args.note)
        print(f"applied {job_id}  {entry['company']}: {entry['title']}")
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
        if meta.get("note"):
            print(f"              note: {meta['note']}")
        if meta.get("url"):
            print(f"              {meta['url']}")
    return 0


# --------------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jobradar", description="Scan company job boards for roles you want.")
    p.add_argument("--config", default=str(DEFAULT_CONFIG), help="config directory")
    p.add_argument("--data", default=str(DEFAULT_DATA), help="data directory (seen/applied logs)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="fetch every board, match, and write the report")
    s.add_argument("--out", default=str(DEFAULT_OUT), help="HTML report path")
    s.add_argument("--markdown", help="also write a markdown digest here")
    s.add_argument("--new-only", action="store_true", help="report only postings never seen before")
    s.add_argument("--print-new", action="store_true", help="print new matches to stdout")
    s.add_argument("--ci", action="store_true", help="skip boards marked `ci: false`")
    s.add_argument("--dry-run", action="store_true", help="don't update the seen log")
    s.set_defaults(func=cmd_scan)

    c = sub.add_parser("check", help="verify every configured board still resolves")
    c.set_defaults(func=cmd_check)

    a = sub.add_parser("applied", help="mark job id(s) or URL(s) as applied")
    a.add_argument("ids", nargs="+")
    a.add_argument("--note", default="", help="free-text note")
    a.set_defaults(func=cmd_applied)

    u = sub.add_parser("unapplied", help="undo an `applied` mark")
    u.add_argument("ids", nargs="+")
    u.set_defaults(func=cmd_unapplied)

    lg = sub.add_parser("log", help="show everything you've applied to")
    lg.set_defaults(func=cmd_log)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
