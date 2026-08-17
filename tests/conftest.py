"""Shared helpers: a fake HTTP layer that replays recorded board responses.

Fixtures live in tests/fixtures/*.json.gz, one per source adapter, captured from the
live APIs (see the capture note in tests/test_sources.py). Each holds the adapter
config, the ordered HTTP responses the live fetch produced, and a snapshot of the
jobs the adapter parsed out of them — so a parser that silently rots fails the suite
instead of shipping an empty board.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import requests

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, spec: dict):
        self.status_code = spec.get("status", 200)
        self.headers = {"content-type": spec.get("content_type", "application/json")}
        self._body = spec.get("body")
        self._text = spec.get("text")

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    @property
    def text(self) -> str:
        if self._text is not None:
            return self._text
        return json.dumps(self._body, ensure_ascii=False)

    def json(self):
        if self._body is not None:
            return self._body
        try:
            return json.loads(self._text or "")
        except json.JSONDecodeError:
            raise ValueError("fixture response is not JSON") from None

    def raise_for_status(self) -> None:
        if not self.ok:
            raise requests.HTTPError(f"{self.status_code} (recorded fixture)")


class Replay:
    """Hands out the recorded responses in order, no matter the URL — adapters make
    their requests sequentially, so FIFO replay mirrors the live capture exactly."""

    def __init__(self, sequence: list[dict]):
        self._seq = [FakeResponse(s) for s in sequence]
        self.requests: list[tuple[str, str]] = []

    def _next(self, method: str, url: str, **kwargs) -> FakeResponse:
        self.requests.append((method, url))
        if not self._seq:
            raise AssertionError(
                f"adapter made more requests than the fixture recorded ({method} {url})"
            )
        return self._seq.pop(0)

    def get(self, url, **kwargs):
        return self._next("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._next("POST", url, **kwargs)


def load_fixture(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)
