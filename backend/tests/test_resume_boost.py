"""Key terms and screening checks (no AI), facts the person adds, and the
tailoring prompt that uses both."""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.security import get_current_user
from app.services import job_terms, resume_customizer, resume_facts

JD = """Senior IT Auditor
Responsibilities: Plan and execute IT general controls (ITGC) audits. Perform risk assessments. Evaluate AWS and Azure security controls.
Requirements:
- 5+ years of experience in IT audit
- Bachelor's degree in Information Systems
- CISA or CISSP certification preferred
- Strong knowledge of NIST, COSO, and SOX 404
- SQL and Python for data analytics
"""
RESUME = "Jane Doe\nIT Auditor, Federal Reserve Bank 2018 – Present. Led SOX and ITGC audits using SQL. CISA. B.S. Accounting.\nAnalyst 2014 - 2018."


def test_key_terms_find_tools_and_standards_not_filler():
    terms = [t.lower() for t in job_terms.key_terms(JD)]
    for want in ("sox", "sql", "python", "nist", "cisa", "aws"):
        assert want in terms
    for filler in ("requirements", "strong", "knowledge", "responsibilities"):
        assert filler not in terms


def test_has_term_is_word_bounded_and_tolerates_plurals():
    assert job_terms.has_term("Ran SOX audits", "sox") and job_terms.has_term("two audit", "audits")
    assert not job_terms.has_term("Used Postgres", "SQL") and not job_terms.has_term("JavaScript", "Java")
    assert job_terms.has_term("risk-management work", "risk management")


def test_coverage_counts_before_and_after():
    cov = job_terms.coverage(JD, "Used SQL", RESUME)
    assert cov["found"] > cov["found_before"] and cov["total"] == len(cov["terms"])


def test_screening_checks_years_degree_and_certs():
    checks = {c["label"]: c for c in job_terms.screening_checks(JD, RESUME, 2026)}
    assert checks["5+ years of experience"]["ok"] is True
    assert checks["Degree"]["ok"] is True and checks["CISA"]["ok"] is True
    assert checks["CISSP"]["ok"] is False
    short = {c["label"]: c for c in job_terms.screening_checks(JD, "Analyst 2024 - Present", 2026)}
    assert short["5+ years of experience"]["ok"] is False and short["Degree"]["ok"] is False


def test_years_shown_counts_overlaps_once():
    assert job_terms.years_shown("A 2015 - 2020, B 2018 - 2022", 2026) == 7


def test_prompt_includes_terms_and_confirmed_facts_and_keeps_honesty_rule():
    p = resume_customizer._build_prompt("resume", {"title": "T", "company": "C", "description": JD},
                                        [{"skill": "Python", "detail": "Built a monthly controls dashboard"}])
    assert "WORDS THE POSTING LEANS ON" in p and "SOX" in p
    assert "EXTRA EXPERIENCE THE CANDIDATE CONFIRMED" in p and "monthly controls dashboard" in p
    assert "Do NOT invent" in p
    plain = resume_customizer._build_prompt("resume", {"title": "T", "company": "C", "description": JD})
    assert "EXTRA EXPERIENCE" not in plain


@pytest.fixture()
def ctx():
    db = SessionLocal()
    user = models.User(email=f"rb-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="Analyst. Used SQL.")
    db.add(user); db.commit(); db.refresh(user)
    job = models.Job(source="t", external_id=uuid.uuid4().hex, title="Senior IT Auditor", company="Acme", description=JD)
    db.add(job); db.commit(); db.refresh(job)
    docx = resume_customizer.build_docx_from_blocks([
        {"type": "name", "text": "Jane Doe"}, {"type": "heading", "text": "Experience"},
        {"type": "entry", "left": "IT Auditor", "right": "2018 – Present"},
        {"type": "bullet", "text": "Led SOX and ITGC audits using SQL"}])
    application = models.Application(user_id=user.id, job_id=job.id, tailored_resume_data=docx, tailored_resume_path="x.docx")
    db.add(application); db.commit(); db.refresh(application)
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app), user, db, application
    app.dependency_overrides.clear()
    db.close()


def test_resume_check_endpoint(ctx):
    c, user, db, application = ctx
    r = c.get(f"/applications/{application.id}/resume-check")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] > 0 and body["found"] >= body["found_before"]
    assert any(t["term"].lower() == "sox" and t["in_tailored"] for t in body["terms"])
    assert any(ch["label"] == "CISSP" and not ch["ok"] for ch in body["checks"])


def test_facts_add_update_delete_and_cap(ctx):
    c, user, db, _ = ctx
    r = c.post("/resume-facts", json={"skill": "Python", "detail": "Built a monthly controls dashboard"})
    assert r.status_code == 200, r.text
    fid = r.json()["id"]
    c.post("/resume-facts", json={"skill": "python", "detail": "Automated evidence collection"})   # same skill: replaces
    facts = resume_facts.for_prompt(db, user.id)
    assert len(facts) == 1 and "Automated" in facts[0]["detail"]
    assert c.post("/resume-facts", json={"skill": "X", "detail": "too short"}).status_code == 422
    assert c.delete(f"/resume-facts/{fid}").status_code == 200
    assert resume_facts.for_prompt(db, user.id) == []
    for i in range(resume_facts.MAX_FACTS):
        resume_facts.add(db, user.id, f"Skill {i}", "Did a real thing here")
    assert c.post("/resume-facts", json={"skill": "One more", "detail": "Another real thing"}).status_code == 400


def test_retailor_passes_the_facts(ctx):
    c, user, db, application = ctx
    resume_facts.add(db, user.id, "Python", "Built a monthly controls dashboard")
    with patch("app.routers.pipeline.resume_customizer.customize_for_job", return_value=("a.docx", b"x", "why")) as m:
        r = c.post(f"/applications/{application.id}/retailor")
    assert r.status_code == 200, r.text
    assert m.call_args.kwargs["facts"][0]["skill"] == "Python"


# ---- ATS readiness number and PDF ---------------------------------------
from app.services import ats_ready


def _fmt(*oks):
    return [{"label": f"f{i}", "ok": ok, "detail": ""} for i, ok in enumerate(oks)]


def test_ready_score_weights_and_label():
    full = ats_ready.compute(_fmt(True, True), {"found": 10, "total": 10}, [{"label": "CISA", "ok": True, "detail": ""}])
    assert full["score"] == 100 and full["label"] == "Strong"
    half_kw = ats_ready.compute(_fmt(True, True), {"found": 5, "total": 10}, [{"label": "CISA", "ok": True, "detail": ""}])
    assert half_kw["score"] == 75 and half_kw["label"] == "Fair" and "key word" in half_kw["next"]
    bad = ats_ready.compute(_fmt(False, False), {"found": 0, "total": 10}, [{"label": "CISSP", "ok": False, "detail": ""}])
    assert bad["score"] == 0 and bad["label"] == "Needs work"


def test_ready_redistributes_when_no_requirements_or_keywords():
    no_req = ats_ready.compute(_fmt(True, True), {"found": 5, "total": 10}, [])
    assert no_req["score"] == round(100 * (30 * 1 + 50 * 0.5) / 80)
    assert [p for p in no_req["parts"] if p["name"] == "Requirements"][0]["score"] is None
    only_fmt = ats_ready.compute(_fmt(True, False), {"found": 0, "total": 0}, [])
    assert only_fmt["score"] == 50


def test_ready_next_step_points_at_the_biggest_loss():
    r = ats_ready.compute(_fmt(True, True), {"found": 10, "total": 10}, [{"label": "CISSP", "ok": False, "detail": ""}])
    assert "CISSP" in r["next"]
    r = ats_ready.compute(_fmt(True, False), {"found": 10, "total": 10}, [])
    assert "format" in r["next"].lower()


def test_resume_check_includes_ready(ctx):
    c, _, _, application = ctx
    body = c.get(f"/applications/{application.id}/resume-check").json()
    assert 0 <= body["ready"]["score"] <= 100 and len(body["ready"]["parts"]) == 3


def test_pdf_has_real_text_in_order_and_downloads(ctx):
    import io
    import pdfplumber
    c, user, db, application = ctx
    r = c.get(f"/applications/{application.id}/tailored-resume.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert 'filename="x.pdf"' in r.headers["content-disposition"]
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        assert len(pdf.pages) == 1
    assert "Jane Doe" in text and "EXPERIENCE" in text and "IT Auditor" in text and "2018" in text
    assert "Led SOX and ITGC audits using SQL" in text
    assert text.index("Jane Doe") < text.index("EXPERIENCE") < text.index("Led SOX")


def test_pdf_escapes_markup_and_needs_a_resume(ctx):
    c, user, db, application = ctx
    blocks = [{"type": "name", "text": "A & B <Co>"}, {"type": "bullet", "text": "R&D <b>bold</b> work"}]
    assert resume_customizer.build_pdf_from_blocks(blocks).startswith(b"%PDF")
    other = models.Application(user_id=user.id, job_id=application.job_id)
    db.add(other); db.commit(); db.refresh(other)
    assert c.get(f"/applications/{other.id}/tailored-resume.pdf").status_code == 404
