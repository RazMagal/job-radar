"""Persistence for the two things worth remembering: what you've seen, what you applied to.

Plain JSON, committed to the repo — so the history of your search is diffable and
survives any hosting change.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import vault
from .models import Job


class Store:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.seen_path = self.dir / "seen.json"
        self.applied_path = self.dir / "applied.json"
        self.applied_enc_path = self.dir / "applied.json.enc"
        self.key = vault.load_key()
        self.seen: dict[str, dict] = self._load(self.seen_path)
        self.applied: dict[str, dict] = self._load_applied()

    @property
    def encrypted(self) -> bool:
        return self.key is not None

    def _load_applied(self) -> dict:
        """With a key, the log lives only as ciphertext — no plaintext on disk, ever."""
        if self.key:
            if self.applied_enc_path.exists():
                raw = vault.decrypt(self.applied_enc_path.read_bytes(), self.key)
                return json.loads(raw.decode("utf-8")) or {}
            # A key is set but nothing encrypted yet: adopt any existing plaintext,
            # so turning encryption on doesn't silently lose the log.
            return self._load(self.applied_path)
        return self._load(self.applied_path)

    def _save_applied(self) -> None:
        if self.key:
            blob = json.dumps(self.applied, indent=2, ensure_ascii=False, sort_keys=True)
            tmp = self.applied_enc_path.with_suffix(".enc.tmp")
            tmp.write_bytes(vault.encrypt(blob.encode("utf-8"), self.key))
            tmp.replace(self.applied_enc_path)
        else:
            self._write(self.applied_path, self.applied)

    @staticmethod
    def _load(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path} is corrupt ({exc}); fix or delete it and re-run") from None
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _write(path: Path, data: dict) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        tmp.replace(path)  # atomic: a killed CI run can't leave a half-written log

    def is_new(self, job: Job) -> bool:
        return job.id not in self.seen and job.id not in self.applied

    def has_applied(self, job_id: str) -> bool:
        return job_id in self.applied

    def record_seen(self, jobs: list[Job], today: str | None = None) -> None:
        stamp = today or date.today().isoformat()
        for j in jobs:
            entry = self.seen.get(j.id)
            if entry:
                entry["last_seen"] = stamp
            else:
                self.seen[j.id] = {
                    "first_seen": stamp,
                    "last_seen": stamp,
                    "company": j.company,
                    "title": j.title,
                    "url": j.url,
                }
        self._write(self.seen_path, self.seen)

    def mark_applied(self, job_id: str, meta: dict, note: str = "") -> dict:
        entry = {
            "applied_on": date.today().isoformat(),
            "company": meta.get("company", ""),
            "title": meta.get("title", ""),
            "url": meta.get("url", ""),
        }
        if note:
            entry["note"] = note
        self.applied[job_id] = entry
        self._save_applied()
        return entry

    def unmark_applied(self, job_id: str) -> bool:
        if job_id not in self.applied:
            return False
        del self.applied[job_id]
        self._save_applied()
        return True

    def lookup(self, needle: str) -> tuple[str, dict] | None:
        """Find a job by id or by URL, in either log."""
        for pool in (self.seen, self.applied):
            if needle in pool:
                return needle, pool[needle]
        for pool in (self.seen, self.applied):
            for jid, meta in pool.items():
                if meta.get("url") == needle:
                    return jid, meta
        return None
