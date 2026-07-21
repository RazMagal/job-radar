"""Command line entry point."""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
from pathlib import Path

import yaml

from . import sources, vault
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

    if args.redact_applied:
        # For the public page: applied jobs are dropped entirely rather than flagged.
        # Publishing `applied: true` would leak where you applied just as surely as
        # publishing the log itself.
        matches = [j for j in matches if not store.has_applied(j.id)]
        payload = [to_payload(j, is_new=store.is_new(j), applied=False) for j in matches]
    else:
        payload = [
            to_payload(j, is_new=store.is_new(j), applied=store.has_applied(j.id)) for j in matches
        ]
    board_failed = len(errors)
    if store.locked:
        # Surfaced on the page's warning strip so it's visible when viewing from a phone.
        errors = errors + [
            {
                "company": "logs",
                "error": "encrypted but no key here — 'new' badges and applied-hiding stay "
                "off until the JOBRADAR_KEY secret is set",
            }
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
    # The locked-log warning isn't a board failure, so it's excluded from this count.
    return 1 if board_failed and board_failed == len(companies) else 0


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


def _locked_bail(store) -> bool:
    if store.locked:
        print(
            f"logs are encrypted but no key is available — set ${vault.KEY_ENV} or restore "
            f"{vault.key_path()}",
            file=sys.stderr,
        )
    return store.locked


def cmd_applied(args) -> int:
    store = Store(Path(args.data))
    if _locked_bail(store):
        return 1
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
    if _locked_bail(store):
        return 1
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
    if _locked_bail(store):
        return 1
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


# -------------------------------------------------------------------------- vault


def cmd_vault_init(args) -> int:
    from . import vault

    key_file = vault.key_path()
    if os.environ.get(vault.KEY_ENV):
        print(f"${vault.KEY_ENV} is already set in this shell; unset it to create a new key.")
        return 1
    if key_file.exists():
        # Overwriting the key would make an existing encrypted log permanently unreadable.
        print(f"A key already exists at {key_file} — refusing to overwrite it.")
        print("Delete it yourself only if you are certain no encrypted log depends on it.")
        return 1

    store = Store(Path(args.data))
    if store.seen_enc_path.exists() or store.applied_enc_path.exists():
        print("An encrypted log already exists in this data dir; refusing to re-init.")
        return 1

    seen, applied = dict(store.seen), dict(store.applied)

    key = vault.generate_key()
    vault.save_key(key)
    store.key = key
    store.seen, store.applied = seen, applied
    store._save_log(store.seen, store.seen_path, store.seen_enc_path)
    store._save_log(store.applied, store.applied_path, store.applied_enc_path)

    print(f"key written to {key_file} (mode 0600)")
    print(f"encrypted: seen.json.enc ({len(seen)} seen), applied.json.enc ({len(applied)} applied)")
    print("plaintext logs removed")
    print()
    print("Back this key up somewhere safe — the logs cannot be recovered without it.")
    print("A password manager entry is ideal: a 44-character string that never changes.")
    print()
    print("To run scans in the cloud / from your phone, the key must be a repo secret,")
    print("or 'new' detection won't work there:")
    print(f"  gh secret set {vault.KEY_ENV} --repo <owner>/<repo> --body '{key.decode()}'")
    return 0


def cmd_vault_status(args) -> int:
    from . import vault

    store = Store(Path(args.data))
    if os.environ.get(vault.KEY_ENV):
        print(f"key:       from ${vault.KEY_ENV}")
    elif vault.key_path().exists():
        print(f"key:       {vault.key_path()}")
    else:
        print("key:       none — logs are stored as plaintext")

    logs = (
        ("seen", store.seen_path, store.seen_enc_path),
        ("applied", store.applied_path, store.applied_enc_path),
    )
    for name, plain, enc in logs:
        mode = "encrypted" if enc.exists() else ("plaintext" if plain.exists() else "absent")
        print(f"{name + ':':10} {mode}")

    if store.locked:
        print(
            "\nlocked: an encrypted log exists but no key is available here — reads return "
            "empty and writes are skipped. Restore the key to unlock."
        )
    else:
        print(f"entries:   {len(store.seen)} seen, {len(store.applied)} applied")

    stale = [n for n, p, e in logs if e.exists() and p.exists()]
    if stale:
        print(f"\nwarning: stale plaintext beside ciphertext for {', '.join(stale)} — delete it.")
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
    s.add_argument(
        "--redact-applied",
        action="store_true",
        help="omit applied jobs from the report entirely (use for any public page)",
    )
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

    v = sub.add_parser("vault", help="encrypt the applied log so a public repo can't leak it")
    vsub = v.add_subparsers(dest="vault_command", required=True)
    vi = vsub.add_parser("init", help="generate a key and encrypt the applied log")
    vi.set_defaults(func=cmd_vault_init)
    vs = vsub.add_parser("status", help="show key and encryption state")
    vs.set_defaults(func=cmd_vault_status)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
