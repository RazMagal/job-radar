"""Recorded-fixture tests: one real captured API response per source adapter.

Each tests/fixtures/<type>.json.gz was recorded from the live board (responses
gzipped verbatim, job arrays trimmed) together with a snapshot of the jobs the
adapter parsed at capture time. If an adapter's parsing silently rots — a renamed
JSON key, a reshuffled positional row — the replay stops matching and the suite
fails, instead of the board shipping as quietly empty.

To refresh after an API change: re-run the capture script (see git history of this
file / the session that added it) or hand-record: run the adapter once with
SESSION.get/post wrapped, dump the responses, snapshot `[j.to_dict() for j in jobs]`.

posted_at is compared only by shape: several boards report relative dates
("Posted 5 Days Ago"), which the adapters resolve against *today*.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import pytest

from jobradar import sources
from jobradar.http import SESSION
from tests.conftest import FIXTURES, Replay, load_fixture

FIXTURE_FILES = sorted(FIXTURES.glob("*.json.gz"))

_ISO_OR_EMPTY = re.compile(r"^(\d{4}-\d{2}-\d{2})?$")


def _without_posted(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "posted_at"}


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.name.split(".")[0])
def test_adapter_parses_recorded_board(path, monkeypatch):
    fx = load_fixture(path)
    replay = Replay(fx["sequence"])
    monkeypatch.setattr(SESSION, "get", replay.get)
    monkeypatch.setattr(SESSION, "post", replay.post)

    jobs = sources.get(fx["cfg"]["type"])(fx["cfg"])
    got = [j.to_dict() for j in jobs]

    for g in got:
        assert _ISO_OR_EMPTY.match(g["posted_at"]), f"bad posted_at: {g['posted_at']!r}"
    assert [_without_posted(g) for g in got] == [_without_posted(e) for e in fx["expected"]]


def test_every_recorded_job_is_wellformed():
    for path in FIXTURE_FILES:
        for job in load_fixture(path)["expected"]:
            assert job["title"], f"{path.name}: job with empty title"
            assert job["url"].startswith("http"), f"{path.name}: non-http url {job['url']!r}"
            assert job["company"], f"{path.name}: job with empty company"


def test_fixture_coverage_does_not_shrink():
    # 14 adapters recorded at capture time; deleting a fixture must be deliberate.
    assert len(FIXTURE_FILES) >= 14


def test_jobspy_keeps_postings_inside_the_hours_old_window(monkeypatch):
    """Regression: timedelta(hours=hours_old/24) rounded to zero days, so every dated
    row not posted *today* was discarded — the 14-day sweeps were silently neutered."""
    jobspy = pytest.importorskip("jobspy")
    pd = pytest.importorskip("pandas")

    rows = [
        {"title": "Verification Engineer", "company": "X", "job_url": "https://x/1",
         "location": "Tel Aviv, Israel", "site": "indeed",
         "date_posted": date.today() - timedelta(days=5)},
        {"title": "Stale Engineer", "company": "Y", "job_url": "https://x/2",
         "location": "Tel Aviv, Israel", "site": "indeed",
         "date_posted": date.today() - timedelta(days=30)},
    ]
    monkeypatch.setattr(jobspy, "scrape_jobs", lambda **kw: pd.DataFrame(rows))

    cfg = {"name": "sweep", "type": "jobspy", "sites": ["indeed"],
           "search_term": "verification", "hours_old": 336}
    titles = [j.title for j in sources.get("jobspy")(cfg)]
    assert titles == ["Verification Engineer"]  # 5 days old survives, 30 days doesn't
