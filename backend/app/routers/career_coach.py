from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import career_coach as career_coach_service
from app.services import usage, rise_index, safety_flags
from app.services import library as library_service

# The individual-product AI Career Coach. Mirrors the Enterprise Job
# Buddy coaching endpoints (routers/job_buddy.py) in shape and in its
# metering discipline -- check_and_increment BEFORE the model call,
# decrement on failure -- but is anchored to a target role the person
# names, not to an Application. See models.CareerCoachSession.
router = APIRouter(prefix="/career-coach", tags=["career-coach"])

ACTION = "career_coach_message"


def _get_owned_session(db: Session, session_id: int, user_id: int) -> models.CareerCoachSession:
    session = db.query(models.CareerCoachSession).filter_by(id=session_id, user_id=user_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Coaching session not found")
    return session


def _history(db: Session, session_id: int, user_id: int) -> list[models.CareerCoachMessage]:
    return db.query(models.CareerCoachMessage).filter_by(
        session_id=session_id, user_id=user_id
    ).order_by(models.CareerCoachMessage.created_at.asc(), models.CareerCoachMessage.id.asc()).all()


def _active_library(db: Session) -> list[models.LibraryItem]:
    return db.query(models.LibraryItem).filter(models.LibraryItem.active.is_(True)).all()


def _messages_out(db: Session, rows: list[models.CareerCoachMessage]) -> list[schemas.CareerCoachMessageOut]:
    """Resolves [[lib:ID]] markers in coach messages into real Library
    items (see services/library.py). One batched lookup for the whole
    transcript; markers pointing at deleted/hidden items just vanish."""
    ids = {int(i) for m in rows for i in library_service.MARKER_RE.findall(m.content or "")}
    by_id = {}
    if ids:
        by_id = {i.id: i for i in db.query(models.LibraryItem).filter(models.LibraryItem.id.in_(ids)).all()}
    out = []
    for m in rows:
        text, items = library_service.resolve(m.content or "", by_id)
        out.append(schemas.CareerCoachMessageOut(
            id=m.id, role=m.role, content=text, created_at=m.created_at,
            resources=[schemas.LibraryItemOut.model_validate(i) for i in items],
        ))
    return out


@router.get("/sessions", response_model=list[schemas.CareerCoachSessionOut])
def list_sessions(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return db.query(models.CareerCoachSession).filter_by(user_id=user.id).order_by(
        models.CareerCoachSession.created_at.desc(), models.CareerCoachSession.id.desc()
    ).all()


@router.post("/sessions", response_model=schemas.CareerCoachStartResponse)
def start_session(
    payload: schemas.CareerCoachStartRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not user.resume_text.strip():
        raise HTTPException(status_code=400, detail="Add your resume before starting a coaching session.")

    usage.check_and_increment(db, user, ACTION, 1)
    target_role = payload.target_role.strip()
    offered = library_service.retrieve(_active_library(db), f"{target_role} {payload.topic}")
    try:
        result = career_coach_service.start_session(
            payload.session_type, target_role, payload.topic, user.resume_text, library=offered,
        )
    except Exception as e:
        usage.decrement(db, user.id, ACTION, 1)
        print(f"[career-coach] Session start failed for user {user.id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Couldn't start a coaching session right now — this attempt wasn't counted against your limit. Try again shortly.",
        )

    session = models.CareerCoachSession(
        user_id=user.id, session_type=payload.session_type,
        target_role=payload.target_role.strip(), topic=result["topic"],
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    opening_text = library_service.strip_unoffered_markers(result["opening_message"], {i.id for i in offered})
    flag = safety_flags.scan(opening_text)
    opening = models.CareerCoachMessage(
        session_id=session.id, user_id=user.id, role="assistant",
        content=opening_text, flagged=bool(flag), flag_reason=flag,
    )
    db.add(opening)
    db.commit()
    db.refresh(opening)
    return schemas.CareerCoachStartResponse(session=session, opening_message=_messages_out(db, [opening])[0])


@router.get("/sessions/{session_id}/messages", response_model=list[schemas.CareerCoachMessageOut])
def get_messages(
    session_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _get_owned_session(db, session_id, user.id)
    return _messages_out(db, _history(db, session_id, user.id))


@router.get("/sessions/{session_id}/library", response_model=list[schemas.LibraryItemOut])
def session_library(
    session_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Library resources relevant to this session's role and topic -- the
    'extra learning' shelf shown beside the chat, independent of whether
    the coach happened to recommend anything in conversation."""
    session = _get_owned_session(db, session_id, user.id)
    return library_service.retrieve(_active_library(db), f"{session.target_role} {session.topic}", limit=5)


@router.post("/sessions/{session_id}/messages", response_model=schemas.CareerCoachMessageOut)
def send_message(
    session_id: int,
    payload: schemas.CoachingMessageRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    session = _get_owned_session(db, session_id, user.id)
    if session.status != "in_progress":
        raise HTTPException(status_code=400, detail="This coaching session has already been completed.")

    usage.check_and_increment(db, user, ACTION, 1)

    history = [{"role": m.role, "content": m.content} for m in _history(db, session_id, user.id)]
    offered = library_service.retrieve(
        _active_library(db), f"{session.target_role} {session.topic} {payload.message}",
    )

    user_flag = safety_flags.scan(payload.message)
    db.add(models.CareerCoachMessage(
        session_id=session_id, user_id=user.id, role="user", content=payload.message,
        flagged=bool(user_flag), flag_reason=user_flag,
    ))
    db.commit()

    try:
        reply_text = career_coach_service.reply(
            session.session_type, session.target_role, session.topic,
            user.resume_text, history, payload.message, library=offered,
        )
        reply_text = library_service.strip_unoffered_markers(reply_text, {i.id for i in offered})
    except Exception as e:
        usage.decrement(db, user.id, ACTION, 1)
        print(f"[career-coach] Reply generation failed for session {session_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Coach couldn't respond right now — this attempt wasn't counted against your limit. Your message was saved; try sending again.",
        )

    reply_flag = safety_flags.scan(reply_text)
    reply_msg = models.CareerCoachMessage(
        session_id=session_id, user_id=user.id, role="assistant", content=reply_text,
        flagged=bool(reply_flag), flag_reason=reply_flag,
    )
    db.add(reply_msg)
    db.commit()
    db.refresh(reply_msg)
    return _messages_out(db, [reply_msg])[0]


@router.post("/sessions/{session_id}/complete", response_model=schemas.CareerCoachSessionOut)
def complete_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    session = _get_owned_session(db, session_id, user.id)
    if session.status != "in_progress":
        return session

    rows = _history(db, session_id, user.id)
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="Exchange at least one reply before ending the session.")
    history = [{"role": m.role, "content": m.content} for m in rows]

    usage.check_and_increment(db, user, ACTION, 1)
    try:
        result = career_coach_service.finish_session(
            session.session_type, session.target_role, session.topic, user.resume_text, history,
        )
    except Exception as e:
        usage.decrement(db, user.id, ACTION, 1)
        print(f"[career-coach] Scoring failed for session {session_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Couldn't score this session right now — this attempt wasn't counted against your limit. Try ending it again shortly.",
        )

    session.status = "completed"
    session.score = result["score"]
    session.feedback = result["feedback"]
    session.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    rise_index.award_points(db, user, "career_coach_session_completed", "Completed a Career Coach session")
    return session


@router.get("/sessions/{session_id}/notes", response_model=schemas.CareerCoachNoteOut)
def get_notes(
    session_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _get_owned_session(db, session_id, user.id)
    note = db.query(models.CareerCoachNote).filter_by(session_id=session_id, user_id=user.id).first()
    return note or schemas.CareerCoachNoteOut()


@router.put("/sessions/{session_id}/notes", response_model=schemas.CareerCoachNoteOut)
def save_notes(
    session_id: int,
    payload: schemas.CareerCoachNoteIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    # Not metered and works on completed sessions too -- people keep
    # annotating after the score. The notes are never sent to the model.
    _get_owned_session(db, session_id, user.id)
    note = db.query(models.CareerCoachNote).filter_by(session_id=session_id, user_id=user.id).first()
    if note:
        note.content = payload.content
        note.updated_at = datetime.utcnow()
    else:
        note = models.CareerCoachNote(session_id=session_id, user_id=user.id, content=payload.content)
        db.add(note)
    db.commit()
    db.refresh(note)
    return note
