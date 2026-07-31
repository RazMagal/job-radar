# SPEC — role-matching engine

The engine decides which job postings are "worth seeing" and tags each kept job with the
single role profile it best matches. This is a pure, deterministic, offline computation:
same inputs → same outputs, no network, no clock.

## Inputs

- **Jobs**: each has at least a `title`, a `location`, and (optionally) a `description`,
  plus identifying fields (company, url). The description is usually empty and is only
  consulted in "deep" mode (below).
- **Settings**: `locations_any` (list of place substrings), `exclude_titles` (list of
  substrings), `min_score` (integer, default **3**).
- **Profiles**: each has an `id`, a `label`, and three keyword lists — `match_any`
  (primary role keywords), `boost` (supporting keywords), `exclude` (disqualifying
  keywords).

Keyword and location comparisons are **case-insensitive substring** matches performed
after normalization (lowercased; punctuation becomes spaces; runs of whitespace
collapse). So keyword `vlsi` matches a title "VLSI Engineer"; keyword `mixed signal`
matches "Mixed-Signal Designer"; keyword `verification` matches "Design Verification
Engineer".

## Title scoring (always applies)

- Each **distinct** `match_any` keyword found in the title is worth **3** points; each
  `boost` keyword found in the title is worth **1** point.
- A profile is a *candidate* for a job only if the title contains **at least one**
  `match_any` keyword. Boost keywords alone never make a profile match.
- Among candidate profiles, the job is tagged with the **highest-scoring** one. The kept
  job exposes that profile's `id` (as its role), `label`, the integer `score`, and the
  list of `matched` keywords.
- The job is **kept only if** the winning score is **≥ `min_score`**.

## Exclusions

- **Global**: if the title contains any `exclude_titles` substring, the job is dropped
  entirely, regardless of any role match.
- **Per-profile**: if the title contains any of a profile's `exclude` substrings, that
  profile is not considered for the job (other profiles may still match it).

## Location filter

- If `locations_any` is non-empty, a job is kept only if its location contains at least
  one of the listed place substrings.
- A job whose location is blank/empty is **always kept** (better a false positive than a
  dropped real match).
- If `locations_any` is empty, every location passes.

## Deep mode — description-based matching (opt-in flag; default OFF)

A flag (default **off**) enables scanning the job description. It **widens** the net; it
never narrows or re-labels what the title already decided.

- **Title stays authoritative.** If the title already qualifies a job for some profile
  (i.e. the title-only result is a match), that classification is returned unchanged and
  the description is **not** used — even if the description is thick with another role's
  vocabulary. A chip role whose blurb name-drops machine-learning stays the chip role.
- **Body pass only as a fallback.** Only when the title qualifies the job for *no* profile
  is the description consulted. A profile then qualifies via the body if the description
  contains at least **two distinct** `match_any` keywords that were **not** already matched
  in the title; each such body keyword is worth **2** points, and the job must still reach
  `min_score` to be kept.
  - "Distinct" collapses overlapping phrases: if `verification` and `design verification`
    are both keywords, a body saying "design verification" counts as **one** distinct body
    keyword, not two — so it alone does not satisfy the "two distinct" bar.
  - If any of a profile's `exclude` substrings appears in the description, the description
    contributes nothing to that profile.
- **Provenance**: keywords that were matched from the description (not the title) appear in
  the kept job's `matched` list marked distinctly with a leading `~` (e.g. `~rtl design`).
- With the flag **off**, descriptions are ignored entirely: results are identical to a
  title-only run.

## Ordering

The batch operation returns the kept jobs **sorted by score, highest first**.

## Acceptance criteria

1. A title containing a primary keyword is kept, tagged with that profile, score ≥ 3.
2. A retitled silicon role — title "VLSI Engineer" — is matched (to the chip-design
   profile), demonstrating the vocabulary catches roles not literally named "verification".
3. A title with only boost keywords and no primary keyword (e.g. "Senior Staff Engineer")
   is **not** matched.
4. A title containing a global `exclude_titles` term (e.g. "Intern") is dropped even when
   it also contains a primary role keyword.
5. A title matching a profile's own `exclude` (e.g. "Software Verification Engineer" for a
   verification profile that excludes "software verification") is not tagged with that
   profile.
6. Location filter: with Israeli place names configured, a "Tel Aviv" job is kept, a "San
   Francisco, CA" job is dropped, and a blank-location job is kept.
7. Deep OFF: a job whose title has no role keyword but whose description is full of role
   vocabulary is **not** matched.
8. Deep ON: that same job **is** matched, tagged with the role its body describes, and the
   body-sourced keywords are marked with `~`.
9. Deep ON, no re-bucketing: a job whose title qualifies it for profile A but whose
   description is dense with profile B vocabulary is still tagged profile A (unchanged from
   the title-only result, no `~` body tags added).
10. Deep ON, "two distinct" bar: a description containing only one distinct primary keyword
    (including the overlapping-phrase case that reduces to one) does not pull the job in.
11. The batch operation returns matches ordered by descending score.
12. Determinism: identical inputs yield identical outputs across repeated calls.
