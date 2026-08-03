"""Rafael Advanced Defense Systems careers — browser-backed (local only).

Rafael's careers site (career.rafael.co.il) has a clean jobs API — /api/jobs, ~320 reqs —
but unlike IAI it sits behind a Reblaze WAF that gates the API route itself: a plain HTTP
GET returns a ~560-byte JS-challenge stub, never the jobs. So this is the one adapter that
drives a **real browser** (Playwright + your installed Chrome) to solve the challenge once,
then reads /api/jobs from inside that browser context.

That makes Rafael deliberately different from every other source:
  * `ci: false` — it needs a browser and a residential-ish IP the challenge will accept.
  * Playwright is an OPTIONAL, heavy dep. Install it only if you want this board:
        pip install playwright        # uses your system Chrome via channel="chrome";
                                      # no extra browser download
    If it's missing, this source fails loudly (SourceError) instead of silently — every
    other board keeps working.
  * Title-only: /api/jobs carries no description (no `--deep`) and no city (Rafael is
    Israel-only, tagged as such). Detail page is /job/{id}.

Content is Hebrew; roles.yaml's Hebrew keywords do the matching. Set `browser_channel:
chromium` in config if you'd rather use a Playwright-managed Chromium than system Chrome.
"""

from __future__ import annotations

from ..models import Job
from .base import SourceError, register

HOME = "https://career.rafael.co.il/"
API = "https://career.rafael.co.il/api/jobs"
JOB_URL = "https://career.rafael.co.il/job/{id}"

_NAV_TIMEOUT = 45_000  # ms — Reblaze challenge + reload can be slow
_POLL_TRIES = 8        # times to re-try the in-page fetch while the challenge settles
_POLL_WAIT = 2_500     # ms between tries

# Runs in the page's JS context (post-challenge cookies, same-origin) — this is the only
# request the WAF actually lets through.
_FETCH_JS = """async () => {
  try {
    const r = await fetch('/api/jobs', {headers: {Accept: 'application/json'}});
    const ct = r.headers.get('content-type') || '';
    if (!r.ok || !ct.includes('json')) return {ok: false, status: r.status};
    return {ok: true, data: await r.json()};
  } catch (e) { return {ok: false, err: String(e)}; }
}"""


def _fetch_payload(cfg: dict):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise SourceError(
            "rafael needs Playwright — its jobs API is behind a Reblaze WAF only a real "
            "browser can pass. Install it (`pip install playwright`) or drop this board; "
            "it's local-only (ci: false) and won't affect any other source."
        ) from e

    channel = cfg.get("browser_channel", "chrome")
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(
                channel=channel,
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
        except Exception as e:
            raise SourceError(
                f"rafael: could not launch a browser (channel={channel!r}): {e}. Install "
                "Chrome, or run `playwright install chromium` and set browser_channel: chromium."
            ) from e
        try:
            page = browser.new_page()
            page.set_default_timeout(_NAV_TIMEOUT)
            page.goto(HOME, wait_until="domcontentloaded")
            for _ in range(_POLL_TRIES):
                try:
                    res = page.evaluate(_FETCH_JS)
                except Exception:
                    res = None  # page may be mid-reload as the challenge resolves
                if res and res.get("ok"):
                    return res["data"]
                page.wait_for_timeout(_POLL_WAIT)
        finally:
            browser.close()
    raise SourceError(
        "rafael: /api/jobs never returned JSON through the browser — the Reblaze challenge "
        "didn't clear (try a non-datacenter IP, or a non-headless run to debug)."
    )


@register("rafael")
def fetch(cfg: dict, deep: bool = False) -> list[Job]:
    payload = _fetch_payload(cfg)
    if not isinstance(payload, list):
        payload = (payload or {}).get("data") or (payload or {}).get("jobs") or []

    jobs: list[Job] = []
    for j in payload:
        jid = j.get("id")
        if jid is None:
            continue
        jobs.append(
            Job(
                company=cfg["name"],
                title=(j.get("tl") or "").replace("\xa0", " ").strip(),
                url=JOB_URL.format(id=jid),
                location="Israel",  # Rafael is Israel-only; the list carries no city
                source="rafael",
                # /api/jobs has no description — title-only, so `deep` is a no-op here.
            )
        )
    return jobs
