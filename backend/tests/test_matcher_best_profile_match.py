"""Tests for matcher.best_profile_match's multi-profile selection logic.

Covers the bug fixed in this PR: with more than one active search
profile at different min_match_score thresholds, best_profile_match
used to pick whichever profile gave the highest RAW score, then check
only THAT profile's threshold -- even when a different active profile
(lower score, but also a lower/looser threshold) would have accepted
the job. That silently downgraded real matches to "near misses" any
time the strictest profile happened to score a job the highest.

score_job (the actual Claude API call) is monkeypatched throughout --
these tests are about the selection logic between profiles, not about
LLM scoring itself, and shouldn't depend on real network/API access.
"""
from unittest.mock import patch

from app.services import matcher

JOB = {
    "title": "Security Engineer", "company": "Acme Corp", "location": "Remote",
    "description": "", "salary_min": None, "salary_max": None,
    "salary_currency": None, "salary_is_predicted": False,
}


def _profile(name, min_match_score=70, locations=None, exclude_companies=None, active=True):
    return {
        "name": name, "active": active,
        "min_match_score": min_match_score,
        "locations": locations if locations is not None else ["Remote"],
        "exclude_companies": exclude_companies or [],
    }


def test_prefers_accepting_profile_over_higher_scoring_rejecting_one():
    """The exact bug scenario: Profile A scores higher (82) but its own
    threshold (90) rejects it. Profile B scores lower (75) but its own
    threshold (70) accepts it. The accepting profile must win."""
    profiles = [
        _profile("Strict", min_match_score=90),
        _profile("Loose", min_match_score=70),
    ]

    def fake_score_job(resume_text, job, profile):
        return {"score": 82, "reason": "r"} if profile["name"] == "Strict" else {"score": 75, "reason": "r"}

    with patch.object(matcher, "score_job", side_effect=fake_score_job):
        result = matcher.best_profile_match(JOB, "resume text", profiles)

    assert result["profile_name"] == "Loose"
    assert result["score"] == 75
    assert result["meets_threshold"] is True


def test_falls_back_to_highest_score_when_none_accept():
    """When no active profile's threshold is cleared, the highest raw
    score is still what's shown as the near-miss -- unchanged
    behavior, just no longer masking a real acceptance elsewhere."""
    profiles = [
        _profile("A", min_match_score=90),
        _profile("B", min_match_score=95),
    ]

    def fake_score_job(resume_text, job, profile):
        return {"score": 82, "reason": "r"} if profile["name"] == "A" else {"score": 60, "reason": "r"}

    with patch.object(matcher, "score_job", side_effect=fake_score_job):
        result = matcher.best_profile_match(JOB, "resume text", profiles)

    assert result["profile_name"] == "A"
    assert result["score"] == 82
    assert result["meets_threshold"] is False


def test_picks_highest_score_among_multiple_accepting_profiles():
    """When more than one profile accepts, the highest-scoring
    acceptance wins -- not just the first one found."""
    profiles = [
        _profile("Low", min_match_score=70),
        _profile("High", min_match_score=70),
    ]

    def fake_score_job(resume_text, job, profile):
        return {"score": 75, "reason": "r"} if profile["name"] == "Low" else {"score": 95, "reason": "r"}

    with patch.object(matcher, "score_job", side_effect=fake_score_job):
        result = matcher.best_profile_match(JOB, "resume text", profiles)

    assert result["profile_name"] == "High"
    assert result["score"] == 95
    assert result["meets_threshold"] is True


def test_single_profile_unaffected():
    """The common single-profile case behaves exactly as before."""
    profiles = [_profile("Only", min_match_score=70)]

    with patch.object(matcher, "score_job", return_value={"score": 80, "reason": "r"}):
        result = matcher.best_profile_match(JOB, "resume text", profiles)

    assert result["profile_name"] == "Only"
    assert result["score"] == 80
    assert result["meets_threshold"] is True


def test_inactive_profile_ignored_even_if_it_would_accept():
    profiles = [
        _profile("Inactive", min_match_score=50, active=False),
        _profile("Active", min_match_score=90),
    ]

    def fake_score_job(resume_text, job, profile):
        return {"score": 99, "reason": "r"} if profile["name"] == "Inactive" else {"score": 60, "reason": "r"}

    with patch.object(matcher, "score_job", side_effect=fake_score_job):
        result = matcher.best_profile_match(JOB, "resume text", profiles)

    assert result["profile_name"] == "Active"
    assert result["meets_threshold"] is False


def test_no_matching_profile_returns_none_with_zero_score():
    profiles = [_profile("WrongLocation", locations=["Chicago"])]

    result = matcher.best_profile_match(
        {**JOB, "location": "Remote"}, "resume text", profiles
    )

    assert result["profile_name"] is None
    assert result["score"] == 0
    assert result["meets_threshold"] is False
