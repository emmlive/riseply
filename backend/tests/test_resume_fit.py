"""Shortening a tailored resume to a page limit, and the ATS checks."""
import json
import random
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app import models
from app.security import get_current_user
from app.services import resume_customizer as rc, usage

WORDS = ("led security audits vulnerability assessments control remediation governance risk cloud IAM "
         "compliance reporting executive stakeholders platform program automated delivered enterprise").split()


def _bullet(rnd, n):
    return " ".join(rnd.choice(WORDS) for _ in range(n)).capitalize() + "."


def make_blocks(bullets_per_role=6, words=24, roles=5, seed=5):
    rnd = random.Random(seed)
    b = [{"type": "name", "text": "Pat Example"},
         {"type": "contact", "text": "pat@example.com  |  (312) 555-0100  |  Chicago, IL"},
         {"type": "heading", "text": "Professional Summary"}, {"type": "text", "text": _bullet(rnd, 45)},
         {"type": "heading", "text": "Professional Experience"}]
    for r in range(roles):
        b += [{"type": "entry", "left": f"Specialist {r}", "right": f"Jan {2024 - r * 3} – Dec {2026 - r * 3}"},
              {"type": "sub", "text": f"Company {r} — Chicago, IL"}]
        b += [{"type": "bullet", "text": _bullet(rnd, words)} for _ in range(bullets_per_role)]
    b += [{"type": "heading", "text": "Education"}, {"type": "entry", "left": "M.S. Cybersecurity", "right": "2020"},
          {"type": "sub", "text": "Missouri State University"}]
    return b


def _fake_client(blocks_out, note="Merged and tightened."):
    c = MagicMock()
    c.messages.create.return_value = MagicMock(content=[MagicMock(text=json.dumps({"note": note, "blocks": blocks_out}))])
    return c


def _shortened(blocks, keep_per_role=3):
    out, seen = [], {}
    role = None
    for b in blocks:
        if b["type"] == "entry":
            role = id(b)
        if b["type"] == "bullet":
            seen[role] = seen.get(role, 0) + 1
            if seen[role] > keep_per_role:
                continue
        out.append(dict(b))
    return out


# --- estimating length -------------------------------------------------------

def test_estimate_grows_with_content():
    assert rc.estimate_pages(make_blocks(2, 14, 2)) < 1.3
    assert rc.estimate_pages(make_blocks(8, 30, 5)) >= 2.8
    assert rc.estimate_pages(make_blocks(3, 20)) < rc.estimate_pages(make_blocks(6, 20))


# --- ATS checks --------------------------------------------------------------

def test_ats_checks_flag_real_problems_and_pass_a_clean_resume():
    clean = rc.ats_checks(make_blocks(3, 18, 3))
    assert all(c["ok"] for c in clean["checks"]), clean

    broken = make_blocks(3, 18, 3)
    broken[1] = {"type": "contact", "text": "Chicago, IL"}
    broken[2] = {"type": "heading", "text": "My Journey"}
    broken[6] = {"type": "entry", "left": "Specialist 0", "right": ""}
    by_label = {c["label"]: c for c in rc.ats_checks(broken)["checks"]}
    assert not by_label["Contact details"]["ok"] and "email" in by_label["Contact details"]["detail"]
    assert not by_label["Standard section names"]["ok"] and "My Journey" in by_label["Standard section names"]["detail"]
    assert not by_label["Dates on every job"]["ok"]


def test_length_check_wants_a_little_headroom_under_two_pages():
    near = make_blocks(5, 26, 5)
    pages = rc.estimate_pages(near)
    by_label = {c["label"]: c for c in rc.ats_checks(near)["checks"]}
    assert by_label["Length"]["ok"] == (pages <= 1.9)


def test_length_check_fails_over_two_pages():
    by_label = {c["label"]: c for c in rc.ats_checks(make_blocks(8, 30, 5))["checks"]}
    assert not by_label["Length"]["ok"] and "USAJOBS" in by_label["Length"]["detail"]


# --- shortening --------------------------------------------------------------

def test_already_short_resume_is_left_alone():
    blocks = make_blocks(2, 14, 2)
    out = rc.fit_to_pages(blocks, {}, 2.0, use_ai=False)
    assert out["blocks"] == blocks and out["fits"] and out["ai_used"] is False


def test_ai_condensing_is_used_when_it_keeps_the_facts(monkeypatch):
    blocks = make_blocks(8, 28, 5)
    assert rc.estimate_pages(blocks) > 2.0
    monkeypatch.setattr(rc, "client", _fake_client(_shortened(blocks, 3)))
    out = rc.fit_to_pages(blocks, {"title": "Security Engineer", "description": "audits risk"}, 2.0)
    assert out["ai_used"] and out["fits"] and out["pages_after"] <= 1.9
    assert out["note"].startswith("Merged and tightened.")
    # every role, company, date and heading survived
    keep = lambda bl, t: [b.get("left") or b.get("text") for b in bl if b["type"] == t]
    assert keep(out["blocks"], "entry") == keep(blocks, "entry")
    assert keep(out["blocks"], "heading") == keep(blocks, "heading")


def test_ai_answer_that_changes_a_title_or_invents_a_number_is_rejected(monkeypatch):
    blocks = make_blocks(8, 28, 5)
    renamed = _shortened(blocks, 3)
    renamed[5]["left"] = "Chief Executive Officer"
    invented = _shortened(blocks, 3)
    next(b for b in invented if b["type"] == "bullet")["text"] = "Cut costs by 87% across the company."
    for bad in (renamed, invented):
        monkeypatch.setattr(rc, "client", _fake_client(bad))
        out = rc.fit_to_pages(blocks, {"title": "x", "description": "y"}, 2.0)
        assert not out["ai_used"]
        assert "87%" not in rc._all_text(out["blocks"]) and "Chief Executive" not in rc._all_text(out["blocks"])
        assert out["fits"] and out["pages_after"] <= 1.9   # the non-AI trim still got it under the limit


def test_trim_keeps_relevant_bullets_and_trims_oldest_roles_first():
    blocks = make_blocks(6, 24, 5)
    # make one old, buried bullet very relevant to the job
    old_idx = [i for i, b in enumerate(blocks) if b["type"] == "bullet"][-3]
    blocks[old_idx]["text"] = "Built Kubernetes terraform pipelines for the platform."
    trimmed, dropped = rc._trim_least_relevant(blocks, "kubernetes terraform engineer", 2.0)
    assert dropped > 0 and rc.estimate_pages(trimmed) <= 2.0
    assert any("Kubernetes" in b.get("text", "") for b in trimmed)
    # every role still has at least two bullets
    counts, role = {}, None
    for b in trimmed:
        if b["type"] == "entry":
            role = b["left"]; counts[role] = 0
        elif b["type"] == "bullet" and role:
            counts[role] += 1
    assert all(c >= 2 for k, c in counts.items() if k.startswith("Specialist"))


# --- endpoint ----------------------------------------------------------------

@pytest.fixture()
def setup():
    db = SessionLocal()
    user = models.User(email=f"fit-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="r")
    db.add(user)
    db.commit()
    db.refresh(user)
    job = models.Job(source="greenhouse", external_id=uuid.uuid4().hex, company="Acme", title="Security Engineer",
                     description="audits risk governance", url="https://x.example/1")
    db.add(job)
    db.commit()
    big = make_blocks(8, 28, 5)
    application = models.Application(user_id=user.id, job_id=job.id, status="pending_approval",
                                      tailored_resume_path="Acme.docx", tailored_resume_data=rc.build_docx_from_blocks(big))
    db.add(application)
    db.commit()
    db.refresh(application)
    app.dependency_overrides[get_current_user] = lambda: user
    yield db, user, application, big, TestClient(app)
    app.dependency_overrides.clear()
    db.close()


def test_preview_now_reports_length_and_ats_checks(setup):
    db, user, application, big, client = setup
    body = client.get(f"/applications/{application.id}/tailored-resume/preview").json()
    assert body["pages"] > 2.0
    assert {c["label"] for c in body["ats"]} >= {"Contact details", "Length", "Plain layout"}


def test_fit_endpoint_proposes_without_saving_and_meters_one_use(setup, monkeypatch):
    db, user, application, big, client = setup
    monkeypatch.setattr(rc, "client", _fake_client(_shortened(big, 3)))
    before_bytes = application.tailored_resume_data
    r = client.post(f"/applications/{application.id}/tailored-resume/fit", json={"pages": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fits"] and body["pages_after"] <= 1.9 < body["pages_before"]
    db.expire_all()
    assert db.get(models.Application, application.id).tailored_resume_data == before_bytes   # nothing saved
    assert usage.get_usage(db, user.id, "tailor_resume") == 1


def test_failed_ai_step_is_not_charged_but_still_shortens(setup, monkeypatch):
    db, user, application, big, client = setup
    broken = MagicMock()
    broken.messages.create.side_effect = RuntimeError("api down")
    monkeypatch.setattr(rc, "client", broken)
    body = client.post(f"/applications/{application.id}/tailored-resume/fit", json={"pages": 2}).json()
    assert body["fits"]
    assert usage.get_usage(db, user.id, "tailor_resume") == 0


def test_fit_rejects_other_page_counts(setup):
    db, user, application, big, client = setup
    assert client.post(f"/applications/{application.id}/tailored-resume/fit", json={"pages": 5}).status_code == 422
