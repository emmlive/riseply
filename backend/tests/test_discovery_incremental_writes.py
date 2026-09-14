"""Tests for run_discovery's refactor to incremental per-source
writes/commits, prompted by a real recurring Render "exceeded its
memory limit" alert.

Previously, run_discovery accumulated every source's raw job data
(all 8 sources: Greenhouse, Lever, RSS, RemoteOK, Arbeitnow, Adzuna
keyword, USAJobs, Adzuna location-paired) into one big list, held
entirely in memory, before writing anything to the database. This is
baseline behavior on every single discovery run (interactive or
scheduled) -- a standing memory cost neither the earlier scheduled-
batch job cap nor the discovery-overlap guard fix touches, since both
of those address different problems entirely. This refactor writes
and commits each source's postings as soon as that source finishes
fetching, so peak memory is bounded by the single largest source
rather than the sum of all 8.

Exercises the real run_discovery function against mocked source
fetchers (not mocking run_discovery itself, unlike
test_pipeline_discover.py and test_scheduled_matching_cap.py, which
both test around it) -- this is specifically testing run_discovery's
own internal behavior.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.services import pipeline_runner
from app import models


@pytest.fixture()
def db():
    with TestClient(app):
        session = SessionLocal()
        yield session
        session.close()


def _job(source, external_id, title="Engineer", company="Acme", location="Remote"):
    return {
        "source": source, "external_id": external_id, "company": company,
        "title": title, "location": location, "url": f"https://example.com/{external_id}",
        "description": "A great role.",
    }


def _patch_all_sources(gh=None, lever_jobs=None, rss=None, remoteok_jobs=None, arbeitnow_jobs=None, adzuna_kw=None, usajobs_jobs=None, adzuna_loc=None):
    """All 8 source fetchers mocked to empty lists by default -- each
    test overrides only the ones it cares about."""
    return [
        patch.object(pipeline_runner.greenhouse, "fetch_all", return_value=gh or []),
        patch.object(pipeline_runner.lever, "fetch_all", return_value=lever_jobs or []),
        patch.object(pipeline_runner.rss_boards, "fetch_all", return_value=rss or []),
        patch.object(pipeline_runner.remoteok, "fetch_jobs", return_value=remoteok_jobs or []),
        patch.object(pipeline_runner.arbeitnow, "fetch_jobs", return_value=arbeitnow_jobs or []),
        patch.object(pipeline_runner.adzuna, "fetch_by_keywords", return_value=adzuna_kw or []),
        patch.object(pipeline_runner.usajobs, "fetch_by_keywords", return_value=usajobs_jobs or []),
        patch.object(pipeline_runner.adzuna, "fetch_by_keyword_location_pairs", return_value=adzuna_loc or []),
    ]


def test_jobs_from_every_source_get_written(db):
    patches = _patch_all_sources(
        gh=[_job("greenhouse", "gh1")],
        lever_jobs=[_job("lever", "lv1")],
        rss=[_job("rss", "rss1")],
        remoteok_jobs=[_job("remoteok", "ro1")],
        arbeitnow_jobs=[_job("arbeitnow", "an1")],
        adzuna_kw=[_job("adzuna", "az1")],
        usajobs_jobs=[_job("usajobs", "us1")],
        adzuna_loc=[_job("adzuna", "az2")],
    )
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
        result = pipeline_runner.run_discovery(db)

    assert result["discovered"] == 8
    assert result["new"] == 8
    written_external_ids = {j.external_id for j in db.query(models.Job).filter(models.Job.external_id.in_(
        ["gh1", "lv1", "rss1", "ro1", "an1", "az1", "us1", "az2"]
    )).all()}
    assert written_external_ids == {"gh1", "lv1", "rss1", "ro1", "an1", "az1", "us1", "az2"}


def test_each_source_commits_independently_not_all_at_the_end(db):
    """The actual point of the refactor -- a later source's fetch
    raising an exception must not roll back an earlier source's
    already-committed jobs, since each source now commits on its own
    rather than sharing one final transaction."""
    patches = _patch_all_sources(gh=[_job("greenhouse", "gh_independent")])
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        with patch.object(pipeline_runner.adzuna, "fetch_by_keyword_location_pairs", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                pipeline_runner.run_discovery(db)

    # Greenhouse's job, fetched and committed BEFORE the later failure,
    # should still be there -- proof its commit was independent.
    found = db.query(models.Job).filter_by(external_id="gh_independent").first()
    assert found is not None


def test_duplicate_jobs_across_the_same_source_still_deduplicated(db):
    """ON CONFLICT DO NOTHING still applies per-source with the new
    incremental commits -- running discovery twice with the same job
    shouldn't create a duplicate row."""
    patches = _patch_all_sources(gh=[_job("greenhouse", "gh_dup")])
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
        pipeline_runner.run_discovery(db)
        result_second = pipeline_runner.run_discovery(db)

    assert result_second["new"] == 0  # already existed, correctly not re-counted as new
    count = db.query(models.Job).filter_by(external_id="gh_dup").count()
    assert count == 1


def test_no_jobs_from_any_source_returns_zero_counts(db):
    patches = _patch_all_sources()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
        result = pipeline_runner.run_discovery(db)

    assert result == {"discovered": 0, "new": 0}
