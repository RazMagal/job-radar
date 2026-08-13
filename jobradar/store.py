"""The applied-jobs log — a local record of what you applied to, with the CV you sent.

Everything here is local and offline. The log lives only on your machine (gitignored,
like cv/) and never reaches the public repo or the cloud scan. "New" detection and
applied-hiding on the page are handled client-side in the browser; this file is only the
durable CLI record — what you applied to, when, which CV — for your own reference and for
correlating CVs with replies later.

Metadata for an id (company/title/url) is resolved from the last scan's data/latest.json,
which every scan writes; that's the catalog the page's ids come from.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


class Store:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.applied_path = self.dir / "applied.json"
        self.latest_path = self.dir / "latest.json"
        self.applied: dict[str, dict] = self._read_json(self.applied_path)

    @staticmethod
    def _read_json(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path} is corrupt ({exc}); fix or delete it and re-run") from None
        return data if isinstance(data, dict) else {}

    def _write_applied(self) -> None:
        tmp = self.applied_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self.applied, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(self.applied_path)  # atomic

    def has_applied(self, job_id: str) -> bool:
        return job_id in self.applied

    def mark_applied(self, job_id: str, meta: dict, note: str = "", cv: str = "") -> dict:
        # Re-marking must not lose what's already recorded: keep the original
        # applied_on, and only overwrite cv/note when new values are actually given.
        prev = self.applied.get(job_id) or {}
        entry = {
            "applied_on": prev.get("applied_on") or date.today().isoformat(),
            "company": meta.get("company") or prev.get("company", ""),
            "title": meta.get("title") or prev.get("title", ""),
            "url": meta.get("url") or prev.get("url", ""),
        }
        if cv or prev.get("cv"):
            entry["cv"] = cv or prev["cv"]  # which CV you sent — the point of the feature
        if note or prev.get("note"):
            entry["note"] = note or prev["note"]
        self.applied[job_id] = entry
        self._write_applied()
        return entry

    def unmark_applied(self, job_id: str) -> bool:
        if job_id not in self.applied:
            return False
        del self.applied[job_id]
        self._write_applied()
        return True

    def _latest_jobs(self) -> list[dict]:
        data = self._read_json(self.latest_path)
        jobs = data.get("jobs")
        return jobs if isinstance(jobs, list) else []

    def lookup(self, needle: str) -> tuple[str, dict] | None:
        """Resolve a job id or URL to (id, metadata).

        Checks the applied log first (so `unapplied`/re-`applied` work without a scan),
        then the last scan's catalog. Returns None if the id/URL isn't known — usually
        means the id is stale or you haven't scanned on this machine yet.
        """
        if needle in self.applied:
            return needle, self.applied[needle]

        for job in self._latest_jobs():
            if job.get("id") == needle or job.get("url") == needle:
                return job["id"], {
                    "company": job.get("company", ""),
                    "title": job.get("title", ""),
                    "url": job.get("url", ""),
                }
        return None
