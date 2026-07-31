"""Acceptance / behavioural tests for the role-matching engine.

Authored BLIND: the author could read only `.confepo/spec-test/contract.md`.
The staged `spec.md` was NOT readable in this environment (the blindness guard
denied it), so the acceptance criteria below are reconstructed from `contract.md`
plus the task brief rather than read verbatim. See the report accompanying this
file for the full list of flags. The most important consequences:

* EXACT point values per keyword are unknown FROM THE CONTRACT. Where a numeric
  threshold is involved these tests bind to *observable* quantities only (the
  `job.score` reported by the engine, and kept-vs-dropped behaviour) instead of
  hard-coding any integer the contract does not promise. The one exception is
  the documented-weights section, where the coordinator supplied the exact,
  documented scoring weights (match_any=3, boost=1, description-only=2) as spec
  facts to pin.

* Assumptions that could not be confirmed against spec.md are marked inline with
  `# ASSUMPTION:` and repeated in the report.

Binding surface (contract.md only):
    jobradar.matcher.load_roles / score / match_all / Settings / Profile
    jobradar.models.Job  -> observe .role, .role_label, .score, .matched
Directly-constructed Settings/Profile use NORMALIZED keywords (lowercase, no
punctuation) exactly as the contract instructs; Job title/location/description
are normalized internally so they are written naturally.
"""

import os

import pytest

from jobradar.matcher import Profile, Settings, load_roles, match_all, score
from jobradar.models import Job


# --------------------------------------------------------------------------- #
# Helpers / fixtures
# --------------------------------------------------------------------------- #

def make_job(title, location="", description="", company="Acme", url="https://example.test/1"):
    """Build a fresh Job. A fresh instance is used per assertion because
    contract.md states score() mutates and returns the passed-in object."""
    return Job(company=company, title=title, url=url,
               location=location, description=description)


def worldwide(min_score=1):
    """Settings that impose no location filter and no title exclusions, so a
    test can isolate matching/scoring behaviour from the filters."""
    return Settings(locations_any=[], exclude_titles=[], min_score=min_score)


HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
CONFIG_PATH = os.path.join(REPO_ROOT, "config", "roles.yaml")


# --------------------------------------------------------------------------- #
# AC: happy path — a title keyword match assigns the role and is kept
# --------------------------------------------------------------------------- #

def test_title_keyword_match_assigns_role_and_is_kept():
    prof = Profile(id="verification", label="Verification",
                   match_any=["verification", "design verification"])
    job = make_job(title="Design Verification Engineer")

    result = score(job, worldwide(), [prof])

    assert result is not None
    assert result.role == "verification"
    assert result.role_label == "Verification"
    assert result.score >= 1
    # a matched title keyword is reported...
    assert "verification" in result.matched
    # ...and title tags carry NO body ("~") prefix.
    assert all(not tag.startswith("~") for tag in result.matched)


def test_match_sets_role_label_distinct_from_id():
    # role_label comes from Profile.label, which may differ from the id.
    prof = Profile(id="verification", label="Hardware Verification",
                   match_any=["verification"])
    job = make_job(title="Verification Engineer")

    result = score(job, worldwide(), [prof])

    assert result is not None
    assert result.role == "verification"
    assert result.role_label == "Hardware Verification"


def test_score_mutates_and_returns_the_same_object():
    prof = Profile(id="verification", label="Verification", match_any=["verification"])
    job = make_job(title="Verification Engineer")

    result = score(job, worldwide(), [prof])

    assert result is job          # same object, per contract
    assert job.role == "verification"


def test_non_matching_job_returns_none():
    prof = Profile(id="verification", label="Verification", match_any=["verification"])
    job = make_job(title="Marketing Manager")

    assert score(job, worldwide(), [prof]) is None


# --------------------------------------------------------------------------- #
# AC: min_score boundary — kept when score >= min_score, dropped when below
# --------------------------------------------------------------------------- #

def test_job_at_exactly_min_score_is_kept_and_one_above_is_dropped():
    # Bind to the OBSERVED score rather than any hard-coded point value:
    # first learn what this job scores, then probe the threshold around it.
    prof = Profile(id="verification", label="Verification", match_any=["verification"])

    observed = score(make_job("Verification Engineer"),
                     Settings(locations_any=[], exclude_titles=[], min_score=0),
                     [prof]).score
    assert observed >= 1  # sanity: a title match earns some points

    # exactly min_score -> KEPT  (ASSUMPTION: threshold is inclusive, i.e. kept
    # iff score >= min_score; "exactly min_score" is called out as a boundary in
    # the brief, which reads as inclusive.)
    kept = score(make_job("Verification Engineer"),
                 Settings(locations_any=[], exclude_titles=[], min_score=observed),
                 [prof])
    assert kept is not None
    assert kept.score == observed

    # one point above the earned score -> DROPPED
    dropped = score(make_job("Verification Engineer"),
                    Settings(locations_any=[], exclude_titles=[], min_score=observed + 1),
                    [prof])
    assert dropped is None


# --------------------------------------------------------------------------- #
# AC: exclude_titles removes a job regardless of keyword match
# --------------------------------------------------------------------------- #

def test_excluded_title_keyword_filters_job_out():
    prof = Profile(id="verification", label="Verification", match_any=["verification"])
    settings = Settings(locations_any=[], exclude_titles=["intern"], min_score=1)
    # Title matches the profile but also contains an excluded word.
    job = make_job(title="Verification Intern")

    assert score(job, settings, [prof]) is None


def test_job_without_excluded_title_is_kept():
    prof = Profile(id="verification", label="Verification", match_any=["verification"])
    settings = Settings(locations_any=[], exclude_titles=["intern"], min_score=1)
    job = make_job(title="Verification Engineer")

    result = score(job, settings, [prof])
    assert result is not None
    assert result.role == "verification"


# --------------------------------------------------------------------------- #
# AC: profile-level exclude disqualifies that profile for the job
# --------------------------------------------------------------------------- #

def test_profile_exclude_keyword_disqualifies_that_profile():
    # "software verification" is excluded even though "verification" matches.
    prof = Profile(id="verification", label="Verification",
                   match_any=["verification", "design verification"],
                   exclude=["software verification"])
    job = make_job(title="Software Verification Engineer")

    # Only that one profile exists, so exclusion leaves nothing to match.
    assert score(job, worldwide(), [prof]) is None


# --------------------------------------------------------------------------- #
# AC: location filtering (locations_any allowlist)
# --------------------------------------------------------------------------- #

def test_location_not_in_allowlist_is_filtered_out():
    prof = Profile(id="verification", label="Verification", match_any=["verification"])
    settings = Settings(locations_any=["tel aviv", "israel"], exclude_titles=[], min_score=1)
    # Keyword matches, but the location is outside the allowlist.
    job = make_job(title="Verification Engineer", location="San Francisco, CA")

    assert score(job, settings, [prof]) is None


def test_location_in_allowlist_is_kept():
    prof = Profile(id="verification", label="Verification", match_any=["verification"])
    settings = Settings(locations_any=["tel aviv", "israel"], exclude_titles=[], min_score=1)
    job = make_job(title="Verification Engineer", location="Tel Aviv, Israel")

    result = score(job, settings, [prof])
    assert result is not None
    assert result.role == "verification"


# --------------------------------------------------------------------------- #
# AC: empty locations_any == worldwide (no location filter)
# --------------------------------------------------------------------------- #

def test_empty_locations_any_means_worldwide():
    prof = Profile(id="verification", label="Verification", match_any=["verification"])
    settings = Settings(locations_any=[], exclude_titles=[], min_score=1)
    # A US location that would be rejected by an allowlist is kept when empty.
    job = make_job(title="Verification Engineer", location="San Francisco, CA")

    result = score(job, settings, [prof])
    assert result is not None
    assert result.role == "verification"


# --------------------------------------------------------------------------- #
# AC: a blank location is kept even when an allowlist is in effect
# --------------------------------------------------------------------------- #

def test_blank_location_is_kept_even_with_location_allowlist():
    prof = Profile(id="verification", label="Verification", match_any=["verification"])
    settings = Settings(locations_any=["tel aviv", "israel"], exclude_titles=[], min_score=1)
    job = make_job(title="Verification Engineer", location="")

    # ASSUMPTION: an empty/blank location is treated as "unknown -> keep", not as
    # "not in allowlist -> drop".
    result = score(job, settings, [prof])
    assert result is not None
    assert result.role == "verification"


# --------------------------------------------------------------------------- #
# AC: deep flag OFF ignores the description entirely
# --------------------------------------------------------------------------- #

def test_deep_flag_off_ignores_description_keywords():
    prof = Profile(id="chip-design", label="Chip Design",
                   match_any=["vlsi", "physical design"])
    # Title has no match; description has two matching keywords.
    job = make_job(title="Hardware Engineer",
                   description="expertise in vlsi and physical design tools")

    # use_description defaults to False -> description not consulted -> no match.
    assert score(job, worldwide(), [prof], use_description=False) is None


def test_deep_flag_off_produces_no_body_tags_even_when_title_matches():
    prof_v = Profile(id="verification", label="Verification", match_any=["verification"])
    prof_ai = Profile(id="ai", label="AI",
                      match_any=["machine learning", "deep learning"])
    # Title matches verification; description is full of AI keywords.
    job = make_job(title="Verification Engineer",
                   description="deep learning and machine learning platform")

    result = score(job, worldwide(), [prof_v, prof_ai], use_description=False)
    assert result is not None
    assert result.role == "verification"
    # With deep off, no "~"-prefixed body tags may appear.
    assert all(not tag.startswith("~") for tag in result.matched)


# --------------------------------------------------------------------------- #
# AC: deep flag ON + exactly two distinct body keywords -> match with ~ tags
# --------------------------------------------------------------------------- #

def test_deep_flag_on_two_distinct_body_keywords_match_with_tilde_tags():
    prof = Profile(id="chip-design", label="Chip Design",
                   match_any=["vlsi", "physical design"])
    # Title has no match; description has exactly two distinct body keywords.
    job = make_job(title="Hardware Engineer",
                   description="expertise in vlsi and physical design tools")

    result = score(job, worldwide(), [prof], use_description=True)
    assert result is not None
    assert result.role == "chip-design"
    # ASSUMPTION: body tag == "~" + normalized keyword.
    assert "~vlsi" in result.matched
    assert "~physical design" in result.matched


# --------------------------------------------------------------------------- #
# AC: exactly one body keyword is NOT enough to bucket a job by its description
# --------------------------------------------------------------------------- #

def test_single_body_keyword_is_insufficient_for_a_match():
    prof = Profile(id="chip-design", label="Chip Design",
                   match_any=["vlsi", "physical design"])
    # Title has no match; description has only ONE matching keyword.
    job = make_job(title="Hardware Engineer",
                   description="expertise in vlsi tooling")

    # ASSUMPTION: a description match requires >= 2 distinct body keywords; a
    # single one does not create a bucket (min_score is low here so the drop is
    # attributable to the two-distinct rule, not the threshold).
    assert score(job, worldwide(), [prof], use_description=True) is None


# --------------------------------------------------------------------------- #
# AC: overlapping body keywords collapse to ONE distinct keyword (deep mode)
#     Spec fact: in the two-distinct rule, keywords where one is a substring of
#     another count as ONE, not two.
# --------------------------------------------------------------------------- #

def test_overlapping_body_keywords_collapse_to_one_and_do_not_match():
    # match_any holds BOTH "verification" and "design verification"; the phrase
    # "design verification" in the body contains both keywords, but they overlap
    # (one is a substring of the other) so they collapse to a SINGLE distinct
    # body keyword -> below the two-distinct bar -> no match.
    prof = Profile(id="verification", label="Verification",
                   match_any=["verification", "design verification"])
    # Title carries no role keyword; body contains only the overlapping phrase.
    job = make_job(title="Hardware Engineer",
                   description="our team practices design verification daily")

    # min_score is low, so a None result is attributable to the overlap-collapse
    # rule (1 distinct keyword), not to the score threshold. A naive counter that
    # treated the two overlapping keywords as two distinct would (wrongly) match.
    assert score(job, worldwide(), [prof], use_description=True) is None


def test_two_non_overlapping_body_keywords_match_with_tilde_tags():
    # Control for the overlap-collapse test: two GENUINELY distinct primary
    # keywords -> two distinct body keywords -> match.
    prof = Profile(id="verification", label="Verification",
                   match_any=["verification", "design verification", "silicon validation"])
    # "design verification" collapses with "verification" into one group;
    # "silicon validation" is a separate, non-overlapping group -> 2 distinct.
    job = make_job(title="Hardware Engineer",
                   description="responsibilities include design verification and silicon validation")

    result = score(job, worldwide(), [prof], use_description=True)
    assert result is not None
    assert result.role == "verification"
    # ~-prefixed body tags are present; the clearly non-overlapping keyword is
    # tagged. (The exact form of the collapsed verification-group tag is left
    # unasserted since the spec does not pin whether it surfaces as
    # "~design verification" or "~verification".)
    assert "~silicon validation" in result.matched
    assert any(tag.startswith("~") and "verification" in tag for tag in result.matched)


# --------------------------------------------------------------------------- #
# AC: no re-bucketing — the title-chosen role is retained even when the body
#     matches a different profile
# --------------------------------------------------------------------------- #

def test_no_rebucketing_title_role_wins_over_body_keywords_of_other_profile():
    prof_v = Profile(id="verification", label="Verification",
                     match_any=["verification", "design verification"])
    prof_cd = Profile(id="chip-design", label="Chip Design",
                      match_any=["vlsi", "physical design"])
    # Title clearly matches verification; description carries two chip-design
    # body keywords that could otherwise pull the job into chip-design.
    job = make_job(title="Design Verification Engineer",
                   description="vlsi and physical design experience required")

    result = score(job, worldwide(), [prof_v, prof_cd], use_description=True)

    assert result is not None
    # ASSUMPTION ("no re-bucketing"): body keywords of a NON-chosen profile do
    # not move the job into that profile's bucket.
    assert result.role == "verification"
    assert result.role_label == "Verification"
    # Those chip-design body keywords belong to a non-chosen profile, so they
    # must NOT appear as this job's matched body tags.
    assert not any("vlsi" in tag or "physical design" in tag for tag in result.matched)


# --------------------------------------------------------------------------- #
# AC: match_all ordering & filtering
# --------------------------------------------------------------------------- #

def test_match_all_sorts_kept_jobs_by_descending_score():
    prof = Profile(id="verification", label="Verification",
                   match_any=["verification", "design verification"])
    settings = Settings(locations_any=[], exclude_titles=[], min_score=1)
    strong = make_job(title="Design Verification Engineer", company="strongco")  # 2 kw
    weak = make_job(title="Verification Analyst", company="weakco")              # 1 kw
    nomatch = make_job(title="Marketing Manager", company="nomatchco")

    results = match_all([weak, strong, nomatch], settings, [prof])

    # non-increasing score order
    scores = [j.score for j in results]
    assert scores == sorted(scores, reverse=True)
    # the non-matching job is excluded
    companies = [j.company for j in results]
    assert "nomatchco" not in companies
    # ASSUMPTION: more distinct matched keywords -> higher score, so the strong
    # job sorts ahead of the weak one.
    assert companies == ["strongco", "weakco"]


def test_match_all_returns_only_kept_jobs():
    prof = Profile(id="verification", label="Verification", match_any=["verification"])
    settings = Settings(locations_any=["tel aviv", "israel"], exclude_titles=["intern"],
                        min_score=1)
    kept = make_job(title="Verification Engineer", location="Tel Aviv", company="keep")
    wrong_loc = make_job(title="Verification Engineer", location="Boston, MA", company="loc")
    excluded_title = make_job(title="Verification Intern", location="Tel Aviv", company="intern")
    no_kw = make_job(title="Chef", location="Tel Aviv", company="chef")

    results = match_all([kept, wrong_loc, excluded_title, no_kw], settings, [prof])

    companies = [j.company for j in results]
    assert companies == ["keep"]


# --------------------------------------------------------------------------- #
# AC: determinism — same inputs twice yield identical results
# --------------------------------------------------------------------------- #

def test_match_all_is_deterministic():
    prof_v = Profile(id="verification", label="Verification",
                     match_any=["verification", "design verification"])
    prof_cd = Profile(id="chip-design", label="Chip Design",
                      match_any=["vlsi", "physical design", "rtl design"])
    settings = Settings(locations_any=[], exclude_titles=[], min_score=1)

    def build_jobs():
        return [
            make_job(title="Design Verification Engineer",
                     description="uvm and rtl design", company="a"),
            make_job(title="VLSI Physical Design Engineer", company="b"),
            make_job(title="Verification Analyst", company="c"),
            make_job(title="Office Manager", company="d"),
        ]

    def observable(jobs):
        return [(j.company, j.role, j.role_label, j.score, list(j.matched)) for j in jobs]

    run1 = observable(match_all(build_jobs(), settings, [prof_v, prof_cd], use_description=True))
    run2 = observable(match_all(build_jobs(), settings, [prof_v, prof_cd], use_description=True))

    assert run1 == run2


# --------------------------------------------------------------------------- #
# AC: documented scoring weights (match_any=3, boost=1, description-only=2).
#     These are documented spec facts, so assert the exact integers.
# --------------------------------------------------------------------------- #

def test_single_title_match_any_keyword_scores_three_points():
    # One match_any keyword in the title, no boost keyword -> exactly 3 points.
    prof = Profile(id="verification", label="Verification",
                   match_any=["verification"], boost=["senior"])
    job = make_job(title="Verification Engineer")  # "verification" only, no "senior"

    result = score(job, worldwide(min_score=1), [prof])
    assert result is not None
    assert result.score == 3


def test_title_match_any_plus_one_boost_keyword_scores_four_points():
    # One match_any keyword (3) + one boost keyword (1) in the title -> 4 points.
    prof = Profile(id="verification", label="Verification",
                   match_any=["verification"], boost=["senior"])
    job = make_job(title="Senior Verification Engineer")  # "verification" + "senior"

    result = score(job, worldwide(min_score=1), [prof])
    assert result is not None
    assert result.score == 4


# --------------------------------------------------------------------------- #
# AC: load_roles error path — no profiles -> ValueError
# --------------------------------------------------------------------------- #

def test_load_roles_raises_valueerror_when_no_profiles(tmp_path):
    # ASSUMPTION: an otherwise-parseable YAML that defines no profiles triggers
    # the documented ValueError. The exact YAML schema is not in the contract,
    # so an empty mapping is used as the clearest "no profiles" input.
    empty = tmp_path / "empty_roles.yaml"
    empty.write_text("{}\n")

    with pytest.raises(ValueError):
        load_roles(str(empty))


# --------------------------------------------------------------------------- #
# Integration tests against the shipped config (facts asserted in contract.md)
# --------------------------------------------------------------------------- #

def test_config_verification_profile_has_expected_keywords():
    _, profiles = load_roles(CONFIG_PATH)
    by_id = {p.id: p for p in profiles}
    assert "verification" in by_id
    v = by_id["verification"]
    assert "verification" in v.match_any
    assert "design verification" in v.match_any
    assert "software verification" in v.exclude


def test_config_chip_design_and_ai_profiles_have_expected_keywords():
    _, profiles = load_roles(CONFIG_PATH)
    by_id = {p.id: p for p in profiles}

    assert "chip-design" in by_id
    cd = by_id["chip-design"]
    for kw in ("vlsi", "physical design", "rtl design"):
        assert kw in cd.match_any

    assert "ai" in by_id
    ai = by_id["ai"]
    for kw in ("machine learning", "deep learning"):
        assert kw in ai.match_any


def test_config_settings_have_expected_defaults_and_locations():
    settings, _ = load_roles(CONFIG_PATH)
    assert "intern" in settings.exclude_titles
    assert settings.min_score == 3
    assert "tel aviv" in settings.locations_any
    assert "israel" in settings.locations_any
    # No US locations present (spot-check of common US identifiers, normalized).
    for us in ("new york", "san francisco", "california", "usa", "united states",
               "boston", "austin"):
        assert us not in settings.locations_any


def test_config_end_to_end_keeps_tel_aviv_verification_job():
    settings, profiles = load_roles(CONFIG_PATH)
    job = make_job(title="Design Verification Engineer", location="Tel Aviv, Israel")

    result = score(job, settings, profiles)
    assert result is not None
    assert result.role == "verification"
    assert result.score >= settings.min_score


def test_config_end_to_end_drops_intern_and_us_location_jobs():
    settings, profiles = load_roles(CONFIG_PATH)

    intern_job = make_job(title="Verification Intern", location="Tel Aviv, Israel")
    assert score(intern_job, settings, profiles) is None

    us_job = make_job(title="Design Verification Engineer", location="Austin, TX")
    assert score(us_job, settings, profiles) is None
