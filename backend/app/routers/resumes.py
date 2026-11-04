"""
Multiple resumes per user, one marked default.

User.resume_text (the field every other part of the app -- matching,
tailoring, interview prep, the extension's scoring and autofill --
already reads directly) is deliberately left completely alone and
untouched by this feature. Instead, _sync_default_to_user() below is
the ONE place responsible for keeping it mirrored to whichever Resume
row is currently is_default, called after every operation that could
change which resume that is (create-as-first, set-default, edit-the-
default, delete-the-default). Every other consumer across the app
keeps working exactly as it did before this feature existed, with zero
changes needed anywhere else.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session, defer

from app.database import get_db
from app.security import get_current_user
from app import models, schemas
from app.services import resume_facts, resume_rewrite, usage

router = APIRouter(prefix="/resumes", tags=["resumes"])


def _sync_default_to_user(db: Session, user: models.User):
    default = db.query(models.Resume).filter_by(user_id=user.id, is_default=True).first()
    user.resume_text = default.resume_text if default else ""
    db.commit()


@router.get("", response_model=list[schemas.SavedResumeOut])
def list_resumes(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Resume)
        .options(defer(models.Resume.file_data))  # the original PDF/Word bytes are never part of the list
        .filter_by(user_id=user.id)
        .order_by(models.Resume.is_default.desc(), models.Resume.created_at.desc())
        .all()
    )


@router.post("", response_model=schemas.SavedResumeOut)
def create_resume(
    payload: schemas.SavedResumeCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    existing_count = db.query(models.Resume).filter_by(user_id=user.id).count()
    resume = models.Resume(
        user_id=user.id,
        label=payload.label.strip() or f"Resume {existing_count + 1}",
        resume_text=payload.resume_text,
        is_default=(existing_count == 0),  # the very first resume a user adds is automatically their default
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    if resume.is_default:
        _sync_default_to_user(db, user)
    return resume


@router.post("/download")
def download_resume_text(
    payload: schemas.ResumeDownloadIn,
    user: models.User = Depends(get_current_user),
):
    """The resume text as the person has it on screen (edited or not), as a Word
    file or an ATS-friendly PDF. Built from what they send, so edits are in it.
    Nothing is saved and no AI is used."""
    import re
    from app.services import resume_customizer
    blocks = resume_customizer.text_to_blocks(payload.text)
    if not blocks:
        raise HTTPException(status_code=422, detail="There's no resume text to download yet.")
    stem = re.sub(r"[^A-Za-z0-9]+", "_", payload.name).strip("_")[:60] or "resume"
    try:
        if payload.format == "pdf":
            data, mime = resume_customizer.build_pdf_from_blocks(blocks), "application/pdf"
        else:
            data, mime = resume_customizer.build_docx_from_blocks(blocks), \
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    except Exception as e:
        print(f"[resumes] download build failed for user {user.id}: {e}")
        raise HTTPException(status_code=422, detail="That couldn't be turned into a file. Try the other format.")
    return Response(content=data, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{stem}.{payload.format}"'})


@router.post("/rewrite", response_model=schemas.ResumeRewriteOut)
def rewrite_resume(
    payload: schemas.ResumeRewriteIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """A rewritten copy of one of the person's resumes, pointed the way they ask.
    Nothing is saved here: they read it, edit it and save it as a new resume.
    Costs one use, refunded when no safe version comes back."""
    if payload.resume_id is not None:
        base = db.query(models.Resume).filter_by(id=payload.resume_id, user_id=user.id).first()
        if not base:
            raise HTTPException(status_code=404, detail="That resume wasn't found. Pick one from your list.")
    else:
        base = db.query(models.Resume).filter_by(user_id=user.id, is_default=True).first()
    base_text = ((base.resume_text if base else user.resume_text) or "").strip()
    base_label = (base.label if base else "") or "My resume"
    if len(base_text) < 80:
        raise HTTPException(status_code=422, detail="Add your resume first, then Riseply can rewrite it.")
    usage.check_and_increment(db, user, "resume_rewrite", 1)
    try:
        label, text = resume_rewrite.rewrite(base_text, payload.focus, resume_facts.for_prompt(db, user.id))
    except ValueError as e:
        usage.decrement(db, user.id, "resume_rewrite", 1)
        raise HTTPException(status_code=502, detail=f"{e} Your resume is unchanged. Try a shorter direction, or try again.")
    except Exception as e:
        usage.decrement(db, user.id, "resume_rewrite", 1)
        print(f"[resume-rewrite] failed for user {user.id}: {e}")
        raise HTTPException(status_code=502, detail="Couldn't rewrite your resume just now. Try again shortly.")
    return schemas.ResumeRewriteOut(label=label, base_label=base_label, resume_text=text)


@router.patch("/{resume_id}", response_model=schemas.SavedResumeOut)
def update_resume(
    resume_id: int,
    payload: schemas.SavedResumeUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    resume = db.query(models.Resume).filter_by(id=resume_id, user_id=user.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")

    if payload.label is not None:
        resume.label = payload.label.strip()
    if payload.resume_text is not None:
        resume.resume_text = payload.resume_text
    db.commit()
    db.refresh(resume)

    if resume.is_default and payload.resume_text is not None:
        _sync_default_to_user(db, user)
    return resume


@router.post("/{resume_id}/set-default", response_model=schemas.SavedResumeOut)
def set_default_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    resume = db.query(models.Resume).filter_by(id=resume_id, user_id=user.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")

    db.query(models.Resume).filter_by(user_id=user.id, is_default=True).update({"is_default": False})
    resume.is_default = True
    db.commit()
    db.refresh(resume)
    _sync_default_to_user(db, user)
    return resume


@router.delete("/{resume_id}")
def delete_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    resume = db.query(models.Resume).filter_by(id=resume_id, user_id=user.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")

    was_default = resume.is_default
    db.delete(resume)
    db.commit()

    if was_default:
        # Promote whichever resume was created most recently among
        # whatever's left, so the account always has SOME default as
        # long as it has any resume at all -- rather than silently
        # leaving every remaining resume non-default and every matching/
        # tailoring/extension call operating on a blank resume until
        # someone notices and picks a new one manually.
        next_default = (
            db.query(models.Resume).filter_by(user_id=user.id)
            .order_by(models.Resume.created_at.desc()).first()
        )
        if next_default:
            next_default.is_default = True
            db.commit()
        _sync_default_to_user(db, user)

    return {"deleted": True}


MAX_FILE_BYTES = 5 * 1024 * 1024
_TYPES = {".pdf": (b"%PDF-", "application/pdf"),
          ".docx": (b"PK", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}


def file_type_for(name: str, data: bytes) -> str | None:
    """The media type if this really is a PDF or Word file, else None. The name
    alone is not trusted: the first bytes have to match too."""
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    magic = _TYPES.get(ext)
    return magic[1] if magic and data.startswith(magic[0]) else None


def _own(db: Session, resume_id: int, user_id: int) -> models.Resume:
    r = db.query(models.Resume).filter_by(id=resume_id, user_id=user_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Resume not found.")
    return r


@router.post("/{resume_id}/file", response_model=schemas.SavedResumeOut)
async def attach_original_file(
    resume_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Keeps the original PDF or Word file with this resume so the browser
    extension can attach it to applications."""
    r = _own(db, resume_id, user.id)
    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="That file is over 5 MB. Use a smaller PDF or Word file.")
    name = (file.filename or "resume").replace("\\", "/").rsplit("/", 1)[-1][:120]
    if not file_type_for(name, data):
        raise HTTPException(status_code=400, detail="Only PDF and Word (.docx) files can be kept.")
    r.file_name, r.file_data = name, data
    db.commit()
    db.refresh(r)
    return r


@router.delete("/{resume_id}/file", response_model=schemas.SavedResumeOut)
def remove_original_file(resume_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    r = _own(db, resume_id, user.id)
    r.file_name, r.file_data = "", None
    db.commit()
    db.refresh(r)
    return r


@router.get("/{resume_id}/file")
def download_original_file(resume_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    r = _own(db, resume_id, user.id)
    if not r.file_data:
        raise HTTPException(status_code=404, detail="No original file is kept for this resume.")
    mime = file_type_for(r.file_name, r.file_data) or "application/octet-stream"
    return Response(content=r.file_data, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{r.file_name}"'})
