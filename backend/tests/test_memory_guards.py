"""Memory guards: the PDF reader stops after a few pages, and the Applications
list reports resume / cover letter flags without loading the big columns."""
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.main import app
from app.database import SessionLocal, engine
from app import models
from app.security import get_current_user
from app.services import resume_parser


def _pdf(pages: int) -> bytes:
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(pages):
        c.drawString(72, 700, f"PAGEMARK{i:02d}")
        c.showPage()
    c.save()
    return buf.getvalue()


def test_pdf_reader_stops_after_the_page_limit():
    text = resume_parser.extract_text_from_pdf(_pdf(resume_parser.MAX_PDF_PAGES + 4))
    assert "PAGEMARK00" in text
    assert f"PAGEMARK{resume_parser.MAX_PDF_PAGES - 1:02d}" in text
    assert f"PAGEMARK{resume_parser.MAX_PDF_PAGES:02d}" not in text


def test_short_pdf_is_read_in_full():
    text = resume_parser.extract_text_from_pdf(_pdf(3))
    assert all(f"PAGEMARK{i:02d}" in text for i in range(3))


@pytest.fixture()
def listing():
    db = SessionLocal()
    user = models.User(email=f"mem-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", resume_text="r")
    db.add(user); db.commit(); db.refresh(user)
    app.dependency_overrides[get_current_user] = lambda: user
    yield db, user, TestClient(app)
    app.dependency_overrides.clear()
    db.close()


def test_list_reports_flags_without_loading_big_columns(listing):
    db, user, client = listing
    def make(data, letter):
        job = models.Job(source="greenhouse", external_id=uuid.uuid4().hex, company="Co", title="T",
                         description="D" * 2000, url=f"https://x.example/{uuid.uuid4().hex}")
        db.add(job); db.commit()
        a = models.Application(user_id=user.id, job_id=job.id, status="approved", tailored_resume_path="a.docx",
                               tailored_resume_data=data, cover_letter=letter, match_score=50)
        db.add(a); db.commit(); return a.id
    both = make(b"x" * 5000, "Dear team")
    neither = make(None, "")

    selects = []
    def grab(conn, cursor, statement, *a):
        selects.append(statement)
    event.listen(engine, "before_cursor_execute", grab)
    try:
        rows = {r["id"]: r for r in client.get("/applications").json()}
    finally:
        event.remove(engine, "before_cursor_execute", grab)

    assert rows[both]["has_tailored_resume_data"] is True and rows[both]["has_cover_letter"] is True
    assert rows[neither]["has_tailored_resume_data"] is False and rows[neither]["has_cover_letter"] is False
    app_sql = [s for s in selects if "FROM applications" in s]
    assert len(app_sql) == 1, "list should be a single query, no per-row lazy loads"
    cols = app_sql[0].split(" FROM ")[0]
    assert "applications.tailored_resume_data," not in cols and "applications.cover_letter," not in cols
    assert "jobs.description" not in cols
