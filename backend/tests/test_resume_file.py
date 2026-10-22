"""Keeping the original resume file and what the extension attaches."""
import base64
import io
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app.main import app as fastapp
from app.database import SessionLocal
from app.security import get_current_user
from app import models
from app.services import resume_pdf

client = TestClient(fastapp)
PDF = b"%PDF-1.4\n" + b"x" * 200


@pytest.fixture()
def db():
    s = SessionLocal(); yield s; s.close()


@pytest.fixture(autouse=True)
def _clear():
    yield
    fastapp.dependency_overrides.clear()


def _user(db, text="Jane Doe\nIT AUDITOR\nAcme 2019-2024"):
    u = models.User(email=f"rf{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", full_name="Jane Doe", resume_text=text)
    db.add(u); db.commit(); db.refresh(u)
    r = models.Resume(user_id=u.id, label="Main", resume_text=text, is_default=True)
    db.add(r); db.commit(); db.refresh(r)
    fastapp.dependency_overrides[get_current_user] = lambda: u
    return u, r


def _up(rid, name, data):
    return client.post(f"/resumes/{rid}/file", files={"file": (name, io.BytesIO(data))})


def test_upload_validates_type_by_content_and_size(db):
    u, r = _user(db)
    assert _up(r.id, "cv.pdf", b"not a pdf").status_code == 400
    assert _up(r.id, "cv.exe", PDF).status_code == 400
    assert _up(r.id, "cv.pdf", b"%PDF-" + b"x" * (5 * 1024 * 1024)).status_code == 400
    ok = _up(r.id, "cv.pdf", PDF)
    assert ok.status_code == 200 and ok.json()["file_name"] == "cv.pdf" and "file_data" not in ok.json()


def test_docx_magic_and_download_and_remove(db):
    u, r = _user(db)
    assert _up(r.id, "cv.docx", b"PK\x03\x04" + b"0" * 50).status_code == 200
    d = client.get(f"/resumes/{r.id}/file")
    assert d.status_code == 200 and d.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert client.delete(f"/resumes/{r.id}/file").json()["file_name"] == ""
    assert client.get(f"/resumes/{r.id}/file").status_code == 404


def test_files_are_private(db):
    u, r = _user(db)
    _up(r.id, "cv.pdf", PDF)
    _user(db)
    assert client.get(f"/resumes/{r.id}/file").status_code == 404
    assert _up(r.id, "cv.pdf", PDF).status_code == 404


def test_extension_gets_uploaded_file_else_generated_pdf(db):
    u, r = _user(db)
    gen = client.get("/extension/resume-file").json()
    assert gen["source"] == "generated" and gen["filename"] == "Jane_Doe_Resume.pdf"
    assert base64.b64decode(gen["data"]).startswith(b"%PDF-")
    _up(r.id, "My Resume.pdf", PDF)
    up = client.get("/extension/resume-file").json()
    assert up["source"] == "uploaded" and up["filename"] == "My Resume.pdf" and base64.b64decode(up["data"]) == PDF


def test_extension_needs_a_resume(db):
    u = models.User(email=f"rf{uuid.uuid4().hex[:8]}@x.com", hashed_password="x", full_name="N", resume_text="")
    db.add(u); db.commit(); db.refresh(u)
    fastapp.dependency_overrides[get_current_user] = lambda: u
    assert client.get("/extension/resume-file").status_code == 400


def test_pdf_builder_handles_odd_text():
    assert resume_pdf.build("A & B <tag>\n\nSKILLS\n- SQL").startswith(b"%PDF-")
    assert resume_pdf.build("").startswith(b"%PDF-")
    assert resume_pdf.safe_filename("José O'Neil") == "Jos_O_Neil_Resume.pdf" and resume_pdf.safe_filename("") == "Resume.pdf"
