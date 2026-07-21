"""Persistence for the two things worth remembering: what you've seen, what you applied to.

Both are JSON. When a vault key is set (see jobradar/vault.py) each log lives only as
ciphertext — data/seen.json.enc and data/applied.json.enc — and the plaintext never
touches disk. Without a key they're plain files. The repo is public, so the encrypted
form is what belongs in git; see HOW_TO.md.

There's a third state: an encrypted log exists but this process has no key (a CI run
where the JOBRADAR_KEY secret isn't set). It can't be read and mustn't be overwritten,
so the store runs "locked" — memory-less, and every write is a no-op — and callers warn.
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
        self.seen_enc_path = self.dir / "seen.json.enc"
        self.applied_path = self.dir / "applied.json"
        self.applied_enc_path = self.dir / "applied.json.enc"
        self.key = vault.load_key()
        self.locked = False  # set when an encrypted log exists but we have no key

        self.seen = self._load_log(self.seen_path, self.seen_enc_path)
        self.applied = self._load_log(self.applied_path, self.applied_enc_path)

    @property
    def encrypted(self) -> bool:
        return self.key is not None

    # -- log I/O -------------------------------------------------------------

    def _load_log(self, plain: Path, enc: Path) -> dict:
        if self.key:
            if enc.exists():
                raw = vault.decrypt(enc.read_bytes(), self.key)
                return json.loads(raw.decode("utf-8")) or {}
            # Key set but nothing encrypted yet: adopt existing plaintext so turning
            # encryption on doesn't silently lose the log.
            return self._read_json(plain)
        if enc.exists():
            # Encrypted, but no key here. We can't read it and must not write plaintext
            # beside it, so run memory-less rather than corrupt the ciphertext.
            self.locked = True
            return {}
        return self._read_json(plain)

    def _save_log(self, data: dict, plain: Path, enc: Path) -> None:
        if self.locked:
            return  # no key: leave the ciphertext untouched rather than clobber it
        blob = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
        if self.key:
            tmp = enc.with_suffix(".enc.tmp")
            tmp.write_bytes(vault.encrypt(blob.encode("utf-8"), self.key))
            tmp.replace(enc)  # atomic
            if plain.exists():
                plain.unlink()  # never leave plaintext beside the ciphertext
        else:
            tmp = plain.with_suffix(plain.suffix + ".tmp")
            tmp.write_text(blob, encoding="utf-8")
            tmp.replace(plain)  # atomic: a killed run can't leave a half-written log

    @staticmethod
    def _read_json(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path} is corrupt ({exc}); fix or delete it and re-run") from None
        return data if isinstance(data, dict) else {}

    # -- queries -------------------------------------------------------------

    def is_new(self, job: Job) -> bool:
        return job.id not in self.seen and job.id not in self.applied

    def has_applied(self, job_id: str) -> bool:
        return job_id in self.applied

    # -- mutations -----------------------------------------------------------

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
        self._save_log(self.seen, self.seen_path, self.seen_enc_path)

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
        self._save_log(self.applied, self.applied_path, self.applied_enc_path)
        return entry

    def unmark_applied(self, job_id: str) -> bool:
        if job_id not in self.applied:
            return False
        del self.applied[job_id]
        self._save_log(self.applied, self.applied_path, self.applied_enc_path)
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
