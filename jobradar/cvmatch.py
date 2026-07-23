"""Pick the best CV for a job by weighted term overlap — deterministic, offline, no LLM.

Reads the actual text of your CVs and scores each job's title+description against them.
The weighting is TF-IDF across your own small CV corpus: a term that appears in *every*
CV (or is generic filler) barely counts, while a term distinctive to one CV — `uvm`,
`pytorch`, `device driver` — carries the signal. The winning CV plus the terms that
tipped it are returned, so every recommendation comes with its reason.

Bigrams ("design verification", "device driver") weigh double — they're far more specific
than the words apart.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# Resume/JD filler and common English. Kept short; TF-IDF suppresses the rest because
# words shared across all CVs get near-zero weight anyway.
STOP = frozenset(
    """
    a an the and or of to in for with on at by from as is are be been being this that
    these those it its we you our your they their he she his her i me my will would can
    could should may might must have has had do does did not no such than then so if
    into over under out up down off about across per via etc eg ie
    experience experienced work working works worked team teams role roles responsible
    responsibilities skills skill ability able strong knowledge understanding using use
    used year years including include includes required requirements requirement based
    development develop developer engineer engineering company job position candidate
    candidates looking join world class leading global new high level ability etc
    """.split()
)

_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.]*")


def tokens(text: str) -> list[str]:
    raw = [t.strip(".") for t in _TOKEN.findall(text.lower())]
    return [t for t in raw if t and (len(t) >= 2 or t in {"c", "r"})]


def _terms(text: str) -> list[str]:
    """Unigrams (minus stopwords) plus bigrams of adjacent content words."""
    toks = tokens(text)
    unis = [t for t in toks if t not in STOP]
    bis = [
        f"{a} {b}"
        for a, b in zip(toks, toks[1:])
        if a not in STOP and b not in STOP and len(a) >= 2 and len(b) >= 2
    ]
    return unis + bis


def _is_bigram(term: str) -> bool:
    return " " in term


@dataclass
class Match:
    label: str
    score: float
    terms: list[str]  # the overlapping terms that drove the pick, strongest first


class CVMatcher:
    def __init__(self, weights: dict[str, dict[str, float]]):
        # weights[label][term] = L2-normalised TF-IDF weight
        self._weights = weights

    @property
    def labels(self) -> list[str]:
        return list(self._weights)

    @classmethod
    def from_texts(cls, texts: dict[str, str]) -> "CVMatcher":
        """texts: {cv_label: full CV text}. Needs at least one non-empty CV."""
        counts: dict[str, dict[str, int]] = {}
        for label, text in texts.items():
            c: dict[str, int] = {}
            for term in _terms(text):
                c[term] = c.get(term, 0) + 1
            counts[label] = c

        counts = {label: c for label, c in counts.items() if c}
        if not counts:
            return cls({})

        n = len(counts)
        df: dict[str, int] = {}
        for c in counts.values():
            for term in c:
                df[term] = df.get(term, 0) + 1

        weights: dict[str, dict[str, float]] = {}
        for label, c in counts.items():
            vec: dict[str, float] = {}
            for term, tf in c.items():
                # With one CV there's nothing to discriminate, so fall back to plain
                # presence (idf would be 0 and zero out every term).
                idf = 1.0 if n == 1 else math.log(n / df[term])
                if idf <= 0:
                    continue  # term in every CV — carries no signal
                vec[term] = tf * idf * (2.0 if _is_bigram(term) else 1.0)
            norm = math.sqrt(sum(w * w for w in vec.values()))
            if norm:
                vec = {t: w / norm for t, w in vec.items()}
            weights[label] = vec
        return cls(weights)

    def rank(self, job_text: str) -> list[Match]:
        """Every CV scored against this job, strongest first."""
        if not self._weights:
            return []
        job = set(_terms(job_text))
        if not job:
            return []

        out = []
        for label, vec in self._weights.items():
            contrib = {t: vec[t] for t in job if t in vec}
            out.append(
                Match(
                    label=label,
                    score=round(sum(contrib.values()), 4),
                    terms=sorted(contrib, key=contrib.get, reverse=True)[:6],
                )
            )
        out.sort(key=lambda m: m.score, reverse=True)
        return out

    def best(self, job_text: str, min_score: float = 0.15) -> Match | None:
        """Best CV for this job, or None if no CV overlaps it meaningfully.

        A None result means "not confident" — the caller falls back to the plain
        role→CV mapping rather than overriding it on weak signal.
        """
        ranked = self.rank(job_text)
        if not ranked or ranked[0].score < min_score:
            return None
        return ranked[0]
