"""Tests for the mentorship feature additions:
- AI-assisted mentor suggestion (mentor_matcher.py + the suggested-mentors endpoint)
- Meeting logging + employee feedback
- Mentorship analytics rollup
- The mentorship check-in reminder job (mentor_reminders.py)

DATABASE_URL is set at MODULE level, same reasoning as
test_internal_scheduled_run.py: app.database's engine is built once at
import time, so a per-test env var change would be too late for an
already-imported module.

get_current_user is overridden via FastAPI's dependency_overrides
rather than exercising real JWT auth -- these tests are about the
mentorship logic, not the auth system (which has its own tests
elsewhere), and a real token adds setup noise without adding coverage.
"""
import uuid
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.security import get_current_user
from app import models
from app.services import mentor_matcher, mentor_reminders

client = TestClient(app)


def _make_user(db, email, resume_text=""):
    user = models.User(email=email, hashed_password="x", resume_text=resume_text)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_org(db, name="Acme Health"):
    org = models.Organization(name=name, join_code=f"CODE{name[:4].upper()}")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_member(db, org_id, user_id, role="admin", department_id=None):
    member = models.OrganizationMember(organization_id=org_id, user_id=user_id, role=role, department_id=department_id)
    db.add(member)
    db.commit()
    return member


def _make_job(db):
    # uuid4 rather than an incrementing counter -- see
    # test_matching_candidate_priority.py's _make_job for why: Job's
    # (source, external_id) uniqueness is global across the whole
    # shared test database, and this file's own counter starting at 1
    # with source="test" collided against that file's identically-
    # patterned counter the moment both files' tests ran together.
    job = models.Job(source="test", external_id=uuid.uuid4().hex, company="Acme", title="Nurse", location="Remote")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _make_application(db, user_id, org_id, department_id=None):
    job = _make_job(db)
    app_row = models.Application(user_id=user_id, job_id=job.id, organization_id=org_id, department_id=department_id)
    db.add(app_row)
    db.commit()
    db.refresh(app_row)
    return app_row


def _make_mentor_contact(db, org_id, name="Mentor One", mentor_bio="10 years in ICU nursing"):
    contact = models.OrgHumanContact(
        organization_id=org_id, name=name, email=f"{name.replace(' ', '').lower()}@acme.com",
        is_mentor=True, mentor_bio=mentor_bio,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@pytest.fixture()
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _login_as(user):
    app.dependency_overrides[get_current_user] = lambda: user


# --- mentor_matcher.py ---

def test_score_mentor_match_parses_valid_response():
    fake_resp = type("R", (), {"content": [type("C", (), {"text": '{"score": 82, "reason": "Strong clinical background overlap."}'})()]})()
    with patch.object(mentor_matcher.client.messages, "create", return_value=fake_resp):
        result = mentor_matcher.score_mentor_match("ICU nurse, 5 years", "Grow into charge nurse", "Charge nurse mentor")
    assert result == {"score": 82, "reason": "Strong clinical background overlap."}


def test_score_mentor_match_raises_on_missing_score():
    fake_resp = type("R", (), {"content": [type("C", (), {"text": '{"reason": "no score field"}'})()]})()
    with patch.object(mentor_matcher.client.messages, "create", return_value=fake_resp):
        with pytest.raises(ValueError):
            mentor_matcher.score_mentor_match("resume", "goal", "bio")


def test_suggest_mentors_ranks_highest_first_and_skips_failures():
    mentor_a = type("M", (), {"id": 1, "name": "A", "email": "a@x.com", "mentor_bio": "bio a"})()
    mentor_b = type("M", (), {"id": 2, "name": "B", "email": "b@x.com", "mentor_bio": "bio b"})()
    mentor_c = type("M", (), {"id": 3, "name": "C", "email": "c@x.com", "mentor_bio": "bio c"})()

    def fake_score(resume, goal, bio):
        if bio == "bio a":
            return {"score": 60, "reason": "ok fit"}
        if bio == "bio b":
            raise RuntimeError("simulated API failure")
        return {"score": 95, "reason": "great fit"}

    with patch.object(mentor_matcher, "score_mentor_match", side_effect=fake_score):
        ranked = mentor_matcher.suggest_mentors("resume", "goal", [mentor_a, mentor_b, mentor_c])

    assert [r["contact_id"] for r in ranked] == [3, 1]  # mentor_b (id 2) skipped, highest score first


# --- suggested-mentors endpoint ---

def test_suggested_mentors_endpoint_returns_ranked_list(db):
    admin = _make_user(db, "admin1@acme.com")
    org = _make_org(db, "OrgA")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "emp1@acme.com", resume_text="ICU nurse, 5 years experience")
    app_row = _make_application(db, employee.id, org.id)
    _make_mentor_contact(db, org.id, "Mentor A", "Charge nurse background")
    _make_mentor_contact(db, org.id, "Mentor B", "ER trauma specialist")

    _login_as(admin)
    with patch.object(mentor_matcher, "score_mentor_match", side_effect=[
        {"score": 70, "reason": "decent fit"}, {"score": 90, "reason": "excellent fit"},
    ]):
        resp = client.get(f"/orgs/{org.id}/employees/{app_row.id}/suggested-mentors")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["score"] == 90  # ranked highest first


def test_suggested_mentors_requires_admin_access(db):
    non_member = _make_user(db, "outsider@x.com")
    org = _make_org(db, "OrgB")
    employee = _make_user(db, "emp2@acme.com")
    app_row = _make_application(db, employee.id, org.id)

    _login_as(non_member)
    resp = client.get(f"/orgs/{org.id}/employees/{app_row.id}/suggested-mentors")
    assert resp.status_code == 403


def test_suggested_mentors_empty_when_no_mentors(db):
    admin = _make_user(db, "admin2@acme.com")
    org = _make_org(db, "OrgC")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "emp3@acme.com")
    app_row = _make_application(db, employee.id, org.id)

    _login_as(admin)
    resp = client.get(f"/orgs/{org.id}/employees/{app_row.id}/suggested-mentors")
    assert resp.status_code == 200
    assert resp.json() == []


# --- meeting logging + feedback ---

def test_log_meeting_and_list_it(db):
    admin = _make_user(db, "admin3@acme.com")
    org = _make_org(db, "OrgD")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "emp4@acme.com")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)

    assignment = models.MentorAssignment(application_id=app_row.id, contact_id=contact.id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    _login_as(admin)
    resp = client.post(
        f"/orgs/{org.id}/mentor-assignments/{assignment.id}/meetings",
        json={"meeting_date": date.today().isoformat(), "notes": "Discussed onboarding progress"},
    )
    assert resp.status_code == 200
    meeting_id = resp.json()["id"]

    list_resp = client.get(f"/orgs/{org.id}/mentor-assignments/{assignment.id}/meetings")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["notes"] == "Discussed onboarding progress"

    return meeting_id  # not used further here, just documents the flow


def test_logging_meeting_resets_reminder_guard(db):
    admin = _make_user(db, "admin4@acme.com")
    org = _make_org(db, "OrgE")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "emp5@acme.com")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)

    assignment = models.MentorAssignment(
        application_id=app_row.id, contact_id=contact.id,
        reminder_last_sent_at=datetime.utcnow(),
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    assert assignment.reminder_last_sent_at is not None

    _login_as(admin)
    client.post(
        f"/orgs/{org.id}/mentor-assignments/{assignment.id}/meetings",
        json={"meeting_date": date.today().isoformat(), "notes": "Check-in"},
    )

    db.refresh(assignment)
    assert assignment.reminder_last_sent_at is None


def test_employee_can_submit_feedback_on_own_meeting(db):
    admin = _make_user(db, "admin5@acme.com")
    org = _make_org(db, "OrgF")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "emp6@acme.com")
    _make_member(db, org.id, employee.id, role="employee")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)
    assignment = models.MentorAssignment(application_id=app_row.id, contact_id=contact.id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    _login_as(admin)
    meeting_resp = client.post(
        f"/orgs/{org.id}/mentor-assignments/{assignment.id}/meetings",
        json={"meeting_date": date.today().isoformat(), "notes": "First meeting"},
    )
    meeting_id = meeting_resp.json()["id"]

    _login_as(employee)
    fb_resp = client.post(
        f"/orgs/{org.id}/mentor-meetings/{meeting_id}/feedback",
        json={"rating": 5, "feedback_note": "Really helpful!"},
    )
    assert fb_resp.status_code == 200
    assert fb_resp.json()["rating"] == 5


def test_other_employee_cannot_submit_feedback_on_someone_elses_meeting(db):
    admin = _make_user(db, "admin6@acme.com")
    org = _make_org(db, "OrgG")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "emp7@acme.com")
    other_employee = _make_user(db, "emp8@acme.com")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)
    assignment = models.MentorAssignment(application_id=app_row.id, contact_id=contact.id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    _login_as(admin)
    meeting_resp = client.post(
        f"/orgs/{org.id}/mentor-assignments/{assignment.id}/meetings",
        json={"meeting_date": date.today().isoformat(), "notes": "Meeting"},
    )
    meeting_id = meeting_resp.json()["id"]

    _login_as(other_employee)
    fb_resp = client.post(
        f"/orgs/{org.id}/mentor-meetings/{meeting_id}/feedback",
        json={"rating": 1, "feedback_note": "not my meeting"},
    )
    assert fb_resp.status_code == 403


# --- analytics rollup ---

def test_analytics_includes_mentorship_stats(db):
    admin = _make_user(db, "admin7@acme.com")
    org = _make_org(db, "OrgH")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "emp9@acme.com")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)
    assignment = models.MentorAssignment(application_id=app_row.id, contact_id=contact.id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    meeting = models.MentorMeetingLog(
        mentor_assignment_id=assignment.id, logged_by_user_id=admin.id,
        meeting_date=date.today(), rating=4,
    )
    db.add(meeting)
    db.commit()

    _login_as(admin)
    resp = client.get(f"/orgs/{org.id}/analytics")
    assert resp.status_code == 200
    m = resp.json()["mentorship"]
    assert m["total_pairings"] == 1
    assert m["total_meetings_logged"] == 1
    assert m["avg_feedback_rating"] == 4.0
    assert m["employees_with_mentor_pct"] == 100.0


# --- mentor_reminders.py ---

def test_reminder_sent_for_stale_pairing_and_guard_prevents_resend(db):
    admin = _make_user(db, "admin8@acme.com")
    org = _make_org(db, "OrgI")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "emp10@acme.com")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)

    assignment = models.MentorAssignment(
        application_id=app_row.id, contact_id=contact.id,
        assigned_at=datetime.utcnow() - timedelta(days=30),
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    assignment_id = assignment.id

    # Asserting on THIS specific assignment's state (not a global
    # reminders_sent/call_count) since run_mentorship_reminders() is
    # intentionally global -- it queries every MentorAssignment, by
    # design, the same way a real daily cron run would. Other tests in
    # this file create their own pairings in the same shared SQLite
    # file; asserting global counts here would make this test's result
    # depend on what other tests happened to run before it.
    with patch("app.services.notifier.send_email") as mock_send:
        mentor_reminders.run_mentorship_reminders(db)

    db.refresh(assignment)
    assert assignment.reminder_last_sent_at is not None
    sent_to = {call.args[0] for call in mock_send.call_args_list}
    assert employee.email in sent_to
    assert contact.email in sent_to

    first_reminder_time = assignment.reminder_last_sent_at

    # Second run: guard should now prevent re-sending for THIS pairing.
    with patch("app.services.notifier.send_email") as mock_send_again:
        mentor_reminders.run_mentorship_reminders(db)

    db.refresh(assignment)
    assert assignment.reminder_last_sent_at == first_reminder_time  # unchanged -- wasn't touched again
    sent_to_second_run = {call.args[0] for call in mock_send_again.call_args_list}
    assert employee.email not in sent_to_second_run
    assert contact.email not in sent_to_second_run


def test_no_reminder_for_recent_pairing(db):
    admin = _make_user(db, "admin9@acme.com")
    org = _make_org(db, "OrgJ")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "emp11@acme.com")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)

    assignment = models.MentorAssignment(
        application_id=app_row.id, contact_id=contact.id,
        assigned_at=datetime.utcnow() - timedelta(days=2),
    )
    db.add(assignment)
    db.commit()

    with patch("app.services.notifier.send_email") as mock_send:
        mentor_reminders.run_mentorship_reminders(db)

    db.refresh(assignment)
    assert assignment.reminder_last_sent_at is None  # never nudged -- too recent
    sent_to = {call.args[0] for call in mock_send.call_args_list}
    assert employee.email not in sent_to
    assert contact.email not in sent_to


def test_no_reminder_when_recent_meeting_logged(db):
    admin = _make_user(db, "admin10@acme.com")
    org = _make_org(db, "OrgK")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "emp12@acme.com")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)

    assignment = models.MentorAssignment(
        application_id=app_row.id, contact_id=contact.id,
        assigned_at=datetime.utcnow() - timedelta(days=60),
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    db.add(models.MentorMeetingLog(
        mentor_assignment_id=assignment.id, logged_by_user_id=admin.id,
        meeting_date=date.today() - timedelta(days=2),
    ))
    db.commit()

    with patch("app.services.notifier.send_email") as mock_send:
        mentor_reminders.run_mentorship_reminders(db)

    db.refresh(assignment)
    assert assignment.reminder_last_sent_at is None  # recent meeting covers the old assignment date
    sent_to = {call.args[0] for call in mock_send.call_args_list}
    assert employee.email not in sent_to
    assert contact.email not in sent_to


# --- PDF export ---

def test_export_meetings_pdf_returns_valid_pdf(db):
    admin = _make_user(db, "admin11@acme.com", resume_text="")
    org = _make_org(db, "OrgL")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "emp13@acme.com")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)
    assignment = models.MentorAssignment(application_id=app_row.id, contact_id=contact.id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    db.add(models.MentorMeetingLog(
        mentor_assignment_id=assignment.id, logged_by_user_id=admin.id,
        meeting_date=date.today(), notes="Covered onboarding progress", rating=4,
    ))
    db.commit()

    _login_as(admin)
    resp = client.get(f"/orgs/{org.id}/mentor-assignments/{assignment.id}/meetings/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content[:4] == b"%PDF"


def test_export_meetings_pdf_works_with_zero_meetings(db):
    admin = _make_user(db, "admin12@acme.com")
    org = _make_org(db, "OrgM")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "emp14@acme.com")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)
    assignment = models.MentorAssignment(application_id=app_row.id, contact_id=contact.id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    _login_as(admin)
    resp = client.get(f"/orgs/{org.id}/mentor-assignments/{assignment.id}/meetings/export")
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


def test_export_meetings_pdf_requires_pairing_access(db):
    outsider = _make_user(db, "outsider2@x.com")
    org = _make_org(db, "OrgN")
    employee = _make_user(db, "emp15@acme.com")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)
    assignment = models.MentorAssignment(application_id=app_row.id, contact_id=contact.id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    _login_as(outsider)
    resp = client.get(f"/orgs/{org.id}/mentor-assignments/{assignment.id}/meetings/export")
    assert resp.status_code == 403


def test_export_meetings_pdf_404_for_unknown_assignment(db):
    admin = _make_user(db, "admin13@acme.com")
    org = _make_org(db, "OrgO")
    _make_member(db, org.id, admin.id, role="admin")

    _login_as(admin)
    resp = client.get(f"/orgs/{org.id}/mentor-assignments/999999/meetings/export")
    assert resp.status_code == 404


# --- Customizable analytics PDF report ---

def test_analytics_pdf_full_report_default_sections(db):
    admin = _make_user(db, "admin14@acme.com")
    org = _make_org(db, "OrgP")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "emp16@acme.com")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)
    assignment = models.MentorAssignment(application_id=app_row.id, contact_id=contact.id)
    db.add(assignment)
    db.commit()

    _login_as(admin)
    resp = client.get(f"/orgs/{org.id}/analytics/export.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_analytics_pdf_single_section_selection(db):
    admin = _make_user(db, "admin15@acme.com")
    org = _make_org(db, "OrgQ")
    _make_member(db, org.id, admin.id, role="admin")

    _login_as(admin)
    resp = client.get(f"/orgs/{org.id}/analytics/export.pdf?sections=mentorship")
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


def test_analytics_pdf_ignores_invalid_section_names(db):
    admin = _make_user(db, "admin16@acme.com")
    org = _make_org(db, "OrgR")
    _make_member(db, org.id, admin.id, role="admin")

    _login_as(admin)
    resp = client.get(f"/orgs/{org.id}/analytics/export.pdf?sections=mentorship,not_a_real_section,")
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


def test_analytics_pdf_requires_admin(db):
    non_admin = _make_user(db, "notadmin@x.com")
    org = _make_org(db, "OrgS")

    _login_as(non_admin)
    resp = client.get(f"/orgs/{org.id}/analytics/export.pdf")
    assert resp.status_code == 403


# --- End-of-pairing retrospective ---
# Org names here deliberately avoid the "Org<letter>" pattern used
# above (and "OrgX/Y/Z"/"Zenith Health" from test_content_categories.py)
# -- see the join_code collision this exact naming scheme caused
# earlier (name[:4].upper() truncation). Using clearly first-4-char-
# distinct words instead of risking another collision as this file
# keeps growing.

def test_end_mentor_assignment_requires_admin(db):
    admin = _make_user(db, "radmin1@acme.com")
    org = _make_org(db, "Tango Health")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "remp1@acme.com")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)
    assignment = models.MentorAssignment(application_id=app_row.id, contact_id=contact.id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    _login_as(employee)
    resp = client.post(f"/orgs/{org.id}/mentor-assignments/{assignment.id}/end", json={"reason": "completed"})
    assert resp.status_code == 403

    _login_as(admin)
    resp = client.post(f"/orgs/{org.id}/mentor-assignments/{assignment.id}/end", json={"reason": "completed"})
    assert resp.status_code == 200
    assert resp.json()["ended_at"] is not None
    assert resp.json()["end_reason"] == "completed"


def test_end_mentor_assignment_404_for_unknown(db):
    admin = _make_user(db, "radmin2@acme.com")
    org = _make_org(db, "Uniform Health")
    _make_member(db, org.id, admin.id, role="admin")

    _login_as(admin)
    resp = client.post(f"/orgs/{org.id}/mentor-assignments/999999/end", json={"reason": "completed"})
    assert resp.status_code == 404


def test_retrospective_blocked_until_pairing_ended(db):
    admin = _make_user(db, "radmin3@acme.com")
    org = _make_org(db, "Victor Health")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "remp3@acme.com")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)
    assignment = models.MentorAssignment(application_id=app_row.id, contact_id=contact.id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    _login_as(employee)
    resp = client.post(
        f"/orgs/{org.id}/mentor-assignments/{assignment.id}/retrospective",
        json={"what_worked": "Good advice", "what_didnt_work": "", "would_recommend_mentor": True},
    )
    assert resp.status_code == 400


def test_retrospective_submit_and_get_employee_only(db):
    admin = _make_user(db, "radmin4@acme.com")
    org = _make_org(db, "Whiskey Health")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "remp4@acme.com")
    other_user = _make_user(db, "outsider3@x.com")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)
    assignment = models.MentorAssignment(application_id=app_row.id, contact_id=contact.id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    _login_as(admin)
    client.post(f"/orgs/{org.id}/mentor-assignments/{assignment.id}/end", json={"reason": "completed"})

    # Non-employee (admin, mentor, or outsider) cannot submit
    _login_as(other_user)
    resp = client.post(
        f"/orgs/{org.id}/mentor-assignments/{assignment.id}/retrospective",
        json={"what_worked": "x", "what_didnt_work": "y", "would_recommend_mentor": True},
    )
    assert resp.status_code == 403

    # Employee can submit and read back their own
    _login_as(employee)
    resp = client.post(
        f"/orgs/{org.id}/mentor-assignments/{assignment.id}/retrospective",
        json={"what_worked": "Great career advice", "what_didnt_work": "Scheduling was tricky", "would_recommend_mentor": True},
    )
    assert resp.status_code == 200
    assert resp.json()["what_worked"] == "Great career advice"

    get_resp = client.get(f"/orgs/{org.id}/mentor-assignments/{assignment.id}/retrospective")
    assert get_resp.status_code == 200
    assert get_resp.json()["would_recommend_mentor"] is True

    # Non-employee cannot read it either -- stricter than meeting feedback
    _login_as(admin)
    get_resp2 = client.get(f"/orgs/{org.id}/mentor-assignments/{assignment.id}/retrospective")
    assert get_resp2.status_code == 403


def test_retrospective_resubmission_updates_rather_than_duplicates(db):
    admin = _make_user(db, "radmin5@acme.com")
    org = _make_org(db, "Xray Clinic Group")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "remp5@acme.com")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)
    assignment = models.MentorAssignment(application_id=app_row.id, contact_id=contact.id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    _login_as(admin)
    client.post(f"/orgs/{org.id}/mentor-assignments/{assignment.id}/end", json={"reason": "completed"})

    _login_as(employee)
    client.post(
        f"/orgs/{org.id}/mentor-assignments/{assignment.id}/retrospective",
        json={"what_worked": "First draft", "what_didnt_work": "", "would_recommend_mentor": False},
    )
    resp = client.post(
        f"/orgs/{org.id}/mentor-assignments/{assignment.id}/retrospective",
        json={"what_worked": "Revised thoughts", "what_didnt_work": "", "would_recommend_mentor": True},
    )
    assert resp.status_code == 200
    assert resp.json()["what_worked"] == "Revised thoughts"
    assert resp.json()["would_recommend_mentor"] is True

    count = db.query(models.MentorRetrospective).filter_by(mentor_assignment_id=assignment.id).count()
    assert count == 1  # updated in place, not duplicated


def test_reassignment_resets_ended_state(db):
    admin = _make_user(db, "radmin6@acme.com")
    org = _make_org(db, "Yankee Wellness")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "remp6@acme.com")
    app_row = _make_application(db, employee.id, org.id)
    contact_a = _make_mentor_contact(db, org.id, "Mentor A", "bio a")
    contact_b = _make_mentor_contact(db, org.id, "Mentor B", "bio b")
    assignment = models.MentorAssignment(application_id=app_row.id, contact_id=contact_a.id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    _login_as(admin)
    client.post(f"/orgs/{org.id}/mentor-assignments/{assignment.id}/end", json={"reason": "completed"})
    db.refresh(assignment)
    assert assignment.ended_at is not None

    resp = client.post(f"/orgs/{org.id}/employees/{app_row.id}/assign-mentor", json={"contact_id": contact_b.id})
    assert resp.status_code == 200
    assert resp.json()["ended_at"] is None
    assert resp.json()["end_reason"] == ""


def test_analytics_reflects_pairings_ended_and_recommend_pct(db):
    admin = _make_user(db, "radmin7@acme.com")
    org = _make_org(db, "Zulu Care Network")
    _make_member(db, org.id, admin.id, role="admin")
    employee = _make_user(db, "remp7@acme.com")
    app_row = _make_application(db, employee.id, org.id)
    contact = _make_mentor_contact(db, org.id)
    assignment = models.MentorAssignment(application_id=app_row.id, contact_id=contact.id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    _login_as(admin)
    client.post(f"/orgs/{org.id}/mentor-assignments/{assignment.id}/end", json={"reason": "completed"})

    _login_as(employee)
    client.post(
        f"/orgs/{org.id}/mentor-assignments/{assignment.id}/retrospective",
        json={"what_worked": "Everything", "what_didnt_work": "", "would_recommend_mentor": True},
    )

    _login_as(admin)
    resp = client.get(f"/orgs/{org.id}/analytics")
    m = resp.json()["mentorship"]
    assert m["pairings_ended"] == 1
    assert m["would_recommend_mentor_pct"] == 100.0
