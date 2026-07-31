# CONTRACT — public surface for the role-matching engine

Black-box boundary. Signatures and data shapes only.

## Test framework & location

- **Framework**: `pytest`.
- **Test directory**: `tests/` at the repo root (create it). Name the file
  `tests/test_matcher.py`.
- Run from the repo root; the package `jobradar` is importable as-is (there is a
  `jobradar/` package directory).

## Public entry points — `jobradar.matcher`

```python
def load_roles(path) -> tuple[Settings, list[Profile]]
    # Parse a YAML roles file into (settings, profiles). Raises ValueError if the file
    # defines no profiles. All keyword/location strings in the returned objects are stored
    # already NORMALIZED (see "Normalization" below).

def score(job: Job,
          settings: Settings,
          profiles: list[Profile],
          use_description: bool = False) -> Job | None
    # Return the SAME job object annotated with its best-matching profile, or None if the
    # job is filtered out. On a match it sets: job.role (profile id, str),
    # job.role_label (str), job.score (int), job.matched (list[str]).

def match_all(jobs,
              settings: Settings,
              profiles: list[Profile],
              use_description: bool = False) -> list[Job]
    # Score every job; return only the kept ones, sorted by descending score.
```

## Data shapes

### `jobradar.matcher.Settings` (dataclass)
```python
Settings(locations_any: list[str] = [],
         exclude_titles: list[str] = [],
         min_score: int = 3)
```

### `jobradar.matcher.Profile` (dataclass)
```python
Profile(id: str,
        label: str = <id>,
        match_any: list[str] = [],
        boost: list[str] = [],
        exclude: list[str] = [])
```

### `jobradar.models.Job` (dataclass)
```python
Job(company: str, title: str, url: str,      # first three positional
    location: str = "", department: str = "", posted_at: str = "",
    source: str = "",
    role: str = "", role_label: str = "", score: int = 0, matched: list[str] = [],
    cv_label: str = "", cv_reason: str = "", description: str = "")
```
After a successful `score()`/`match_all()`, read `job.role`, `job.role_label`,
`job.score`, `job.matched` on the returned object(s).

## Normalization (critical for building fixtures)

Comparisons are done in a normalized form: **lowercased, punctuation replaced by spaces,
whitespace collapsed and trimmed**. `load_roles(...)` applies this to every keyword and
location it reads, so config-loaded profiles already compare case-insensitively.

If you construct `Settings`/`Profile` **directly** in a test, supply keyword and location
strings **already in normalized form** (lowercase, no punctuation) — e.g.
`match_any=["design verification", "verification"]`, `exclude=["software verification"]`,
`locations_any=["tel aviv", "israel"]`. Job `title`/`location`/`description` values are
normalized internally, so those may be written naturally (e.g. title "VLSI Engineer").

## Two ways to build role fixtures (either is fine)

1. **Direct construction** (self-contained, preferred for unit behaviors): build small
   `Settings` and `Profile` objects inline with normalized keywords, exactly the vocabulary
   a given test needs.
2. **Load the shipped config**: call `load_roles("config/roles.yaml")` at test runtime.
   (Your test process can read that file even though this authoring step cannot.) For
   assertions against the shipped config, these facts hold in it:
   - a profile with id `verification` whose `match_any` includes `verification` and
     `design verification`, and whose `exclude` includes `software verification`;
   - a profile with id `chip-design` whose `match_any` includes `vlsi`, `physical design`,
     `rtl design`;
   - a profile with id `ai` whose `match_any` includes `machine learning`, `deep learning`;
   - `settings.exclude_titles` includes `intern`; `settings.min_score` is `3`;
   - `settings.locations_any` includes `tel aviv` and `israel` but no US locations.

## Notes

- `score()` mutates and returns the passed-in `Job`; use a fresh `Job` per assertion.
- `match_all` accepts any iterable of `Job`.
- No implementation internals (helpers, control flow, point-summing order) are part of this
  contract — bind only to the observable outputs described here and in `spec.md`.
