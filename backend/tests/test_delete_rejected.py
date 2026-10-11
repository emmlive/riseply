"""Deleting rejected jobs: frees the stored files, leaves every list, never comes back."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app import models
from app.security import get_current_user


@pytest.fixture()
def setup():
    db = SessionLocal()
    user = models.User(email=f"del-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="r")
    db.add(user); db.commit(); db.refresh(user)

    def make(status, **kw):
        job = models.Job(source="greenhouse", external_id=uuid.uuid4().hex, company="Co", title=f"T-{status}",
                         description="d", url=f"https://x.example/{uuid.uuid4().hex}")
        db.add(job); db.commit()
        a = models.Application(user_id=user.id, job_id=job.id, status=status, tailored_resume_path="a.docx",
                               tailored_resume_data=b"x" * 5000, cover_letter="Dear...", notes="n",
                               match_reason="because", **kw)
        db.add(a); db.commit(); db.refresh(a)
        return a

    app.dependency_overrides[get_current_user] = lambda: user
    yield db, user, make, TestClient(app)
    app.dependency_overrides.clear()
    db.close()


def test_delete_rejected_wipes_content_hides_it_and_keeps_a_slim_row(setup):
    db, user, make, client = setup
    a = make("rejected")
    keep = make("approved")
    assert client.delete(f"/applications/{a.id}").status_code == 200
    db.expire_all()
    row = db.get(models.Application, a.id)
    assert row is not None and row.deleted_at is not None          # slim row stays: the job never comes back
    assert row.tailored_resume_data is None and row.cover_letter == "" and row.notes == ""
    ids = {x["id"] for x in client.get("/applications").json()} | {x["id"] for x in client.get("/applications?archived=true").json()}
    assert a.id not in ids and keep.id in ids
    assert client.delete(f"/applications/{a.id}").status_code == 404


def test_only_rejected_can_be_deleted(setup):
    db, user, make, client = setup
    for status in ("pending_approval", "approved", "submitted", "interviewing", "accepted"):
        a = make(status)
        assert client.delete(f"/applications/{a.id}").status_code == 409
        db.expire_all()
        assert db.get(models.Application, a.id).deleted_at is None


def test_org_linked_application_is_not_deletable(setup):
    db, user, make, client = setup
    org = models.Organization(name="Org " + uuid.uuid4().hex[:6], join_code=uuid.uuid4().hex[:8])
    db.add(org); db.commit()
    a = make("rejected", organization_id=org.id)
    assert client.delete(f"/applications/{a.id}").status_code == 409


def test_someone_elses_application_is_404(setup):
    db, user, make, client = setup
    a = make("rejected")
    other = models.User(email=f"o-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x")
    db.add(other); db.commit(); db.refresh(other)
    app.dependency_overrides[get_current_user] = lambda: other
    assert client.delete(f"/applications/{a.id}").status_code == 404


def test_delete_all_rejected_includes_archived_and_spares_the_rest(setup):
    db, user, make, client = setup
    r1, r2 = make("rejected"), make("rejected", is_archived=True)
    ok = make("pending_approval")
    r = client.post("/applications/delete-rejected")
    assert r.status_code == 200 and r.json()["deleted"] == 2
    db.expire_all()
    assert db.get(models.Application, r1.id).deleted_at and db.get(models.Application, r2.id).deleted_at
    assert db.get(models.Application, ok.id).deleted_at is None
    assert client.post("/applications/delete-rejected").json()["deleted"] == 0


def test_a_deleted_link_can_be_added_again(setup, monkeypatch):
    db, user, make, client = setup
    a = make("rejected")
    job = db.get(models.Job, a.job_id)
    client.delete(f"/applications/{a.id}")
    # the duplicate-link check ignores deleted rows
    from app.routers import pipeline
    dup = db.query(models.Application.id).join(models.Job, models.Application.job_id == models.Job.id).filter(
        models.Application.user_id == user.id, models.Job.url == job.url, models.Application.deleted_at.is_(None)).first()
    assert dup is None
