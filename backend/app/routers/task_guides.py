import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import doc_export, draft_text
from app.services import task_guide as task_guide_service
from app.services import usage

# "My manager gave me this and I don't know where to start." Saved guides, so
# reopening one is free. Building one counts as a task_guide; each question or
# piece of work sent for review counts as a coaching message.
router = APIRouter(prefix="/task-guides", tags=["task-guides"])

BUILD_ACTION = "task_guide"
HELP_ACTION = "coaching_message"
REVIEW_ACTION = "task_review"


def _get(db: Session, user_id: int, guide_id: int) -> models.TaskGuide:
    row = db.query(models.TaskGuide).filter_by(id=guide_id, user_id=user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Guide not found")
    return row


def _done(row: models.TaskGuide) -> list[str]:
    try:
        v = json.loads(row.done or "[]")
        return [str(i) for i in v] if isinstance(v, list) else []
    except Exception:
        return []


def _out(row: models.TaskGuide) -> schemas.TaskGuideOut:
    data = json.loads(row.data or "{}")
    data.pop("title", None)
    try:
        review = json.loads(row.review) if row.review else None
    except Exception:
        review = None
    return schemas.TaskGuideOut(
        id=row.id, title=row.title, task_text=row.task_text, role=row.role, level=row.level,
        created_at=row.created_at, done=_done(row), review=review if isinstance(review, dict) else None, **data,
    )


@router.get("", response_model=list[schemas.TaskGuideListItem])
def list_guides(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = db.query(models.TaskGuide).filter_by(user_id=user.id).order_by(models.TaskGuide.id.desc()).limit(30).all()
    out = []
    for r in rows:
        try:
            steps = json.loads(r.data or "{}").get("steps", [])
        except Exception:
            steps = []
        ids = {s.get("id") for s in steps if isinstance(s, dict)}
        out.append(schemas.TaskGuideListItem(
            id=r.id, title=r.title or "Task", created_at=r.created_at,
            steps=len(steps), done=len([d for d in _done(r) if d in ids]),
        ))
    return out


@router.get("/{guide_id}", response_model=schemas.TaskGuideOut)
def get_guide(guide_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _out(_get(db, user.id, guide_id))


@router.post("", response_model=schemas.TaskGuideOut)
def build(payload: schemas.TaskGuideRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    usage.check_and_increment(db, user, BUILD_ACTION, 1)
    try:
        data = task_guide_service.build(payload.task.strip(), payload.role.strip(), payload.level, user.resume_text or "")
    except Exception as e:
        usage.decrement(db, user.id, BUILD_ACTION, 1)
        print(f"[task_guide] build failed for user {user.id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Couldn't build the guide right now, and this attempt wasn't counted against your limit. Try again shortly.",
        )
    row = models.TaskGuide(
        user_id=user.id, title=data["title"], task_text=payload.task.strip(), role=payload.role.strip(),
        level=payload.level, data=json.dumps(data), done="[]",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.put("/{guide_id}/progress", response_model=schemas.TaskGuideOut)
def save_progress(guide_id: int, payload: schemas.TaskGuideProgress, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = _get(db, user.id, guide_id)
    valid = {s["id"] for s in json.loads(row.data or "{}").get("steps", [])}
    row.done = json.dumps([d for d in dict.fromkeys(payload.done) if d in valid])
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/{guide_id}/help", response_model=schemas.TaskGuideHelpOut)
def help_with_step(guide_id: int, payload: schemas.TaskGuideHelpRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = _get(db, user.id, guide_id)
    usage.check_and_increment(db, user, HELP_ACTION, 1)
    try:
        reply = task_guide_service.help_reply(
            row.task_text, json.loads(row.data or "{}"), payload.step_id, payload.message,
            [t.model_dump() for t in payload.history], row.level,
        )
    except Exception as e:
        usage.decrement(db, user.id, HELP_ACTION, 1)
        print(f"[task_guide] help failed for guide {guide_id}: {e}")
        raise HTTPException(status_code=502, detail="Couldn't get an answer right now, and this wasn't counted against your limit. Try again shortly.")
    return schemas.TaskGuideHelpOut(reply=reply)


@router.post("/{guide_id}/review", response_model=schemas.TaskGuideOut)
async def review_draft(
    guide_id: int,
    file: UploadFile | None = File(default=None),
    text: str = Form(default=""),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Check a finished draft (an attached file or pasted text) against the guide's
    requirements. The latest review is kept with the guide."""
    row = _get(db, user.id, guide_id)
    draft = ""
    if file is not None and file.filename:
        try:
            draft = draft_text.extract(file.filename, await file.read())
        except draft_text.DraftError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if not draft:
        draft = (text or "").strip()[:draft_text.MAX_CHARS]
    if len(draft) < 40:
        raise HTTPException(status_code=400, detail="Attach your draft or paste at least a few sentences of it to review.")

    usage.check_and_increment(db, user, REVIEW_ACTION, 1)
    try:
        review = task_guide_service.review(row.task_text, json.loads(row.data or "{}"), draft, row.level)
    except Exception as e:
        usage.decrement(db, user.id, REVIEW_ACTION, 1)
        print(f"[task_guide] review failed for guide {guide_id}: {e}")
        raise HTTPException(status_code=502, detail="Couldn't review your draft right now, and this wasn't counted against your limit. Try again shortly.")
    row.review = json.dumps({**review, "reviewed_at": datetime.utcnow().isoformat(), "source": (file.filename if file and file.filename else "pasted text")})
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/{guide_id}")
def delete_guide(guide_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = _get(db, user.id, guide_id)
    db.delete(row)
    db.commit()
    return {"ok": True}


_TYPES = {
    "md": "text/markdown; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _file(data: bytes | str, fmt: str, name: str) -> Response:
    body = data.encode("utf-8") if isinstance(data, str) else data
    return Response(content=body, media_type=_TYPES[fmt], headers={
        "Content-Disposition": f'attachment; filename="{doc_export.safe_name(name, fmt)}"',
        "Cache-Control": "no-store",
    })


def _render(md: str, fmt: str, title: str) -> bytes | str:
    if fmt == "md":
        return md
    blocks = doc_export.parse(md)
    return {"docx": doc_export.to_docx, "pdf": doc_export.to_pdf, "xlsx": doc_export.to_xlsx}[fmt](blocks, title)


@router.get("/{guide_id}/export")
def export_guide(
    guide_id: int,
    format: str = Query("docx", pattern="^(docx|pdf|md)$"),
    include_templates: bool = False,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """The whole guide (steps ticked as saved) as a file to keep, print or send."""
    row = _get(db, user.id, guide_id)
    data = json.loads(row.data or "{}")
    md = doc_export.guide_markdown(data, _done(row), include_materials=include_templates)
    return _file(_render(md, format, row.title), format, f"{row.title or 'task-guide'} steps")


@router.get("/{guide_id}/materials/{index}/export")
def export_material(
    guide_id: int,
    index: int,
    format: str = Query("docx", pattern="^(docx|pdf|xlsx|md)$"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """One template as Word, PDF, Excel (its tables become sheets) or markdown."""
    row = _get(db, user.id, guide_id)
    mats = json.loads(row.data or "{}").get("materials", [])
    if index < 0 or index >= len(mats):
        raise HTTPException(status_code=404, detail="Template not found")
    m = mats[index]
    return _file(_render(m["template"], format, m["name"]), format, m["name"])


@router.get("/{guide_id}/share-text")
def share_text(guide_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = _get(db, user.id, guide_id)
    return {"text": doc_export.share_text(json.loads(row.data or "{}"), _done(row))}
