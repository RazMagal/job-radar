"""Google Careers — the `batchexecute` RPC behind the careers results page.

Google retired its clean `/api/v3/search`; the careers site now server-renders and the
only public JSON job-data call is a `batchexecute` RPC returning keyless positional
arrays. The `rpcids` build id can change on a Google deploy — this is the single most
fragile source here — so parsing is defensive and a shape/id change raises a SourceError
loudly (check surfaces it) rather than silently returning nothing. Still worth it: ~100
Israel roles incl. silicon validation, CPU design verification, TPU, SoC power.

If it ever fails, re-harvest RPC from a live careers-page `batchexecute` request.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ..http import SESSION, TIMEOUT
from ..models import Job
from .base import SourceError, html_to_text, register

RPC = "r06xKb"
URL = (
    "https://www.google.com/about/careers/applications/_/HiringCportalFrontendUi/"
    "data/batchexecute"
)
JOB_URL = "https://www.google.com/about/careers/applications/jobs/results/{id}"
# A browser-ish UA; Google's front door is fussier than a plain ATS JSON endpoint.
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
MAX_PAGES = 15


def _epoch(v) -> str:
    """Dates arrive as [seconds, nanos]."""
    try:
        return datetime.fromtimestamp(int(v[0]), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, IndexError, OSError):
        return ""


def _unwrap(text: str) -> list:
    """Pull our RPC payload out of the batchexecute envelope (`)]}'` + framed chunks)."""
    if text.startswith(")]}'"):
        text = text[text.find("\n") + 1 :]
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("[["):
            continue
        try:
            frames = json.loads(line)
        except ValueError:
            continue
        for fr in frames:
            if isinstance(fr, list) and len(fr) >= 3 and fr[0] == "wrb.fr" and fr[1] == RPC:
                return json.loads(fr[2])
    raise SourceError(
        f"google: no {RPC!r} frame in the batchexecute response — the RPC id likely "
        "changed on a Google deploy; re-harvest it from the careers page"
    )


@register("google")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    location = cfg.get("location", "Israel")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "User-Agent": BROWSER_UA,
    }
    jobs: list[Job] = []
    total = None
    for page in range(1, MAX_PAGES + 1):
        inner = json.dumps([[None, None, None, None, "en", None, [[location]], page]])
        freq = json.dumps([[[RPC, inner, None, "3"]]])
        r = SESSION.post(
            URL,
            params={
                "rpcids": RPC,
                "source-path": "/about/careers/applications/jobs/results",
                "hl": "en",
                "rt": "c",
            },
            data={"f.req": freq},
            headers=headers,
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        payload = _unwrap(r.text)
        rows = payload[0] if payload and isinstance(payload[0], list) else []
        if total is None and len(payload) > 2:
            total = payload[2]
        if not rows:
            break
        bad_rows = 0
        for j in rows:
            try:
                locs = j[9] or []
                job = Job(
                    company=cfg["name"],
                    title=j[1] or "",
                    url=JOB_URL.format(id=j[0]),
                    location=(locs[0][0] if locs and locs[0] else ""),
                    posted_at=_epoch(j[14]) or _epoch(j[12]),
                    source="google",
                )
                if deep and len(j) > 10 and isinstance(j[10], list) and len(j[10]) > 1:
                    job.description = html_to_text(j[10][1] or "")
                jobs.append(job)
            except (IndexError, TypeError):
                bad_rows += 1
                continue  # one malformed row must not sink the page
        # ...but ALL rows failing means the positional row shape changed — say so
        # loudly instead of returning an empty board that reads as "no jobs".
        if rows and bad_rows == len(rows):
            raise SourceError(
                f"google: all {bad_rows} rows in a page failed to parse — the RPC "
                "row shape likely changed on a Google deploy"
            )
        if total is not None and len(jobs) >= total:
            break

    if not jobs and (total or 0) > 0:
        raise SourceError(
            f"google: the RPC reports {total} jobs but none could be read — the "
            "payload shape likely changed on a Google deploy"
        )
    return jobs
