from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user

# Study folders and saved Career Coach notes. Everything here is the
# person's own material: never sent to the model, never metered.
router = APIRouter(prefix="/career-coach/study", tags=["career-coach"])

MAX_FOLDERS = 50
MAX_NOTES = 500


def _folder(db: Session, user_id: int, folder_id: int) -> models.StudyFolder:
    f = db.query(models.StudyFolder).filter_by(id=folder_id, user_id=user_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="Folder not found")
    return f


def _note(db: Session, user_id: int, note_id: int) -> models.StudyNote:
    n = db.query(models.StudyNote).filter_by(id=note_id, user_id=user_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Note not found")
    return n


def _check_name_free(db: Session, user_id: int, name: str, ignore_id: int | None = None) -> None:
    q = db.query(models.StudyFolder.id).filter(
        models.StudyFolder.user_id == user_id,
        func.lower(models.StudyFolder.name) == name.lower(),
    )
    if ignore_id is not None:
        q = q.filter(models.StudyFolder.id != ignore_id)
    if q.first():
        raise HTTPException(status_code=409, detail="You already have a folder with that name.")


def _folder_out(db: Session, f: models.StudyFolder) -> schemas.StudyFolderOut:
    count = db.query(func.count(models.StudyNote.id)).filter_by(user_id=f.user_id, folder_id=f.id).scalar() or 0
    return schemas.StudyFolderOut(id=f.id, name=f.name, note_count=count, created_at=f.created_at)


@router.get("/folders", response_model=list[schemas.StudyFolderOut])
def list_folders(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    folders = db.query(models.StudyFolder).filter_by(user_id=user.id).order_by(func.lower(models.StudyFolder.name)).all()
    return [_folder_out(db, f) for f in folders]


@router.post("/folders", response_model=schemas.StudyFolderOut, status_code=201)
def create_folder(
    payload: schemas.StudyFolderIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    name = " ".join(payload.name.split())
    if not name:
        raise HTTPException(status_code=422, detail="Give the folder a name.")
    if db.query(func.count(models.StudyFolder.id)).filter_by(user_id=user.id).scalar() >= MAX_FOLDERS:
        raise HTTPException(status_code=400, detail=f"You can have up to {MAX_FOLDERS} folders. Delete one you don't use first.")
    _check_name_free(db, user.id, name)
    f = models.StudyFolder(user_id=user.id, name=name)
    db.add(f)
    db.commit()
    db.refresh(f)
    return _folder_out(db, f)


@router.patch("/folders/{folder_id}", response_model=schemas.StudyFolderOut)
def rename_folder(
    folder_id: int,
    payload: schemas.StudyFolderIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    f = _folder(db, user.id, folder_id)
    name = " ".join(payload.name.split())
    if not name:
        raise HTTPException(status_code=422, detail="Give the folder a name.")
    _check_name_free(db, user.id, name, ignore_id=f.id)
    f.name = name
    db.commit()
    db.refresh(f)
    return _folder_out(db, f)


@router.delete("/folders/{folder_id}", status_code=204)
def delete_folder(
    folder_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Deleting a folder never deletes the notes inside it -- they move to
    Unfiled."""
    f = _folder(db, user.id, folder_id)
    db.query(models.StudyNote).filter_by(user_id=user.id, folder_id=f.id).update(
        {models.StudyNote.folder_id: None}, synchronize_session=False)
    db.delete(f)
    db.commit()


@router.get("/notes", response_model=list[schemas.StudyNoteOut])
def list_notes(
    folder_id: int | None = Query(default=None, description="A folder id; leave out for all notes"),
    unfiled: bool = False,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = db.query(models.StudyNote).filter_by(user_id=user.id)
    if unfiled:
        q = q.filter(models.StudyNote.folder_id.is_(None))
    elif folder_id is not None:
        q = q.filter(models.StudyNote.folder_id == folder_id)
    return q.order_by(models.StudyNote.updated_at.desc(), models.StudyNote.id.desc()).all()


@router.post("/notes", response_model=schemas.StudyNoteOut, status_code=201)
def create_note(
    payload: schemas.StudyNoteIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if payload.folder_id is not None:
        _folder(db, user.id, payload.folder_id)
    if payload.session_id is not None:
        if not db.query(models.CareerCoachSession.id).filter_by(id=payload.session_id, user_id=user.id).first():
            raise HTTPException(status_code=404, detail="Coaching session not found")
    if db.query(func.count(models.StudyNote.id)).filter_by(user_id=user.id).scalar() >= MAX_NOTES:
        raise HTTPException(status_code=400, detail=f"You can keep up to {MAX_NOTES} saved notes. Delete some you no longer need.")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="There's nothing to save yet.")
    title = payload.title.strip() or content.splitlines()[0][:80]
    note = models.StudyNote(
        user_id=user.id, folder_id=payload.folder_id, session_id=payload.session_id,
        title=title, content=content, source=payload.source, source_label=payload.source_label.strip(),
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.patch("/notes/{note_id}", response_model=schemas.StudyNoteOut)
def update_note(
    note_id: int,
    payload: schemas.StudyNoteUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    note = _note(db, user.id, note_id)
    sent = payload.model_fields_set
    if "folder_id" in sent:
        if payload.folder_id is not None:
            _folder(db, user.id, payload.folder_id)
        note.folder_id = payload.folder_id
    if "title" in sent and payload.title is not None:
        note.title = payload.title.strip()
    if "content" in sent and payload.content is not None:
        if not payload.content.strip():
            raise HTTPException(status_code=422, detail="A note can't be empty. Delete it instead.")
        note.content = payload.content.strip()
    note.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(note)
    return note


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(
    note_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    db.delete(_note(db, user.id, note_id))
    db.commit()
