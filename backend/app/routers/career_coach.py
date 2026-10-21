import json
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import career_coach as career_coach_service
from app.services import usage, rise_index, safety_flags
from app.services import library as library_service
from app.services import visuals as visuals_service
from app.services import discord_notify
from app.services import videos as videos_service
from app.services import coach_notebook, lesson as lesson_service

# The individual-product AI Career Coach. Mirrors the Enterprise Job
# Buddy coaching endpoints (routers/job_buddy.py) in shape and in its
# metering discipline -- check_and_increment BEFORE the model call,
# decrement on failure -- but is anchored to a target role the person
# names, not to an Application. See models.CareerCoachSession.
router = APIRouter(prefix="/career-coach", tags=["career-coach"])

ACTION = "career_coach_message"


def _notebook_items(db: Session, user: models.User, session_type: str) -> list[dict]:
    """The coach's notes for learning sessions, when the person keeps them on."""
    if session_type in career_coach_service.IN_CHARACTER:
        return []
    row = coach_notebook.get_row(db, user.id)
    return coach_notebook.items_of(row) if row.enabled else []


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


def _delivery_of(m: models.CareerCoachMessage) -> schemas.DeliveryStats | None:
    if not (m.delivery or "").strip():
        return None
    try:
        return schemas.DeliveryStats(**json.loads(m.delivery))
    except Exception:
        return None


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
        text, visual = visuals_service.extract(text)
        out.append(schemas.CareerCoachMessageOut(
            id=m.id, role=m.role, content=text, created_at=m.created_at,
            resources=[schemas.LibraryItemOut.model_validate(i) for i in items],
            visual=visual,
            delivery=_delivery_of(m),
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
    notes = _notebook_items(db, user, payload.session_type)
    offered = library_service.retrieve(_active_library(db), f"{target_role} {payload.topic}")
    try:
        result = career_coach_service.start_session(
            payload.session_type, target_role, payload.topic, user.resume_text, library=offered,
            learning_style=payload.learning_style, voice=payload.voice, notebook=notes,
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
        learning_style=payload.learning_style,
        plan=lesson_service.dump(result["goals"]) if result.get("goals") else "",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    opening_text = visuals_service.sanitize(
        library_service.strip_unoffered_markers(result["opening_message"], {i.id for i in offered})
    )
    opening_text = career_coach_service.limit_cues(opening_text)
    opening_text = career_coach_service.strip_praise_opener(opening_text, payload.session_type)
    if payload.voice:
        opening_text = career_coach_service.plain_for_voice(opening_text)
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
    payload: schemas.CareerCoachMessageRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    session = _get_owned_session(db, session_id, user.id)
    if session.status != "in_progress":
        raise HTTPException(status_code=400, detail="This coaching session has already been completed.")

    usage.check_and_increment(db, user, ACTION, 1)

    history = [{"role": m.role, "content": m.content} for m in _history(db, session_id, user.id)]
    notes = _notebook_items(db, user, session.session_type)
    offered = library_service.retrieve(
        _active_library(db), f"{session.target_role} {session.topic} {payload.message}",
    )

    user_flag = safety_flags.scan(payload.message)
    db.add(models.CareerCoachMessage(
        session_id=session_id, user_id=user.id, role="user", content=payload.message,
        flagged=bool(user_flag), flag_reason=user_flag,
        delivery=payload.delivery.model_dump_json() if payload.delivery else "",
    ))
    db.commit()

    try:
        reply_text = career_coach_service.reply(
            session.session_type, session.target_role, session.topic,
            user.resume_text, history, payload.message, library=offered,
            learning_style=session.learning_style or "auto", style=payload.style, voice=payload.voice,
            visual_kind=payload.visual_kind, notebook=notes, plan=session.lesson,
        )
        plan = session.lesson
        if plan and session.session_type in lesson_service.LESSON_TYPES:
            reply_text, done = lesson_service.extract_covered(reply_text, len(plan["goals"]))
            if done - set(plan.get("covered") or []):
                session.plan = lesson_service.dump(plan["goals"], set(plan.get("covered") or []) | done)
                db.commit()
        else:
            reply_text, _ = lesson_service.extract_covered(reply_text, 0)
        reply_text = visuals_service.sanitize(
            library_service.strip_unoffered_markers(reply_text, {i.id for i in offered})
        )
        reply_text = career_coach_service.limit_cues(reply_text)
        reply_text = career_coach_service.strip_praise_opener(reply_text, session.session_type)
        if payload.voice:
            reply_text = career_coach_service.plain_for_voice(reply_text)
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
    out = _messages_out(db, [reply_msg])[0]
    out.lesson = session.lesson
    return out


@router.post("/sessions/{session_id}/complete", response_model=schemas.CareerCoachSessionOut)
def complete_session(
    session_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    session = _get_owned_session(db, session_id, user.id)
    if session.status != "in_progress":
        return session

    rows = _history(db, session_id, user.id)
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="Exchange at least one reply before ending the session.")
    history = [{"role": m.role, "content": m.content, "delivery": _delivery_of(m)} for m in rows]

    usage.check_and_increment(db, user, ACTION, 1)
    nb_row = None
    remember = False
    if session.session_type not in career_coach_service.IN_CHARACTER:
        nb_row = coach_notebook.get_row(db, user.id)
        remember = bool(nb_row.enabled)
    try:
        result = career_coach_service.finish_session(
            session.session_type, session.target_role, session.topic, user.resume_text, history,
            notebook=coach_notebook.items_of(nb_row) if remember else None, remember=remember,
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
    if remember:
        try:
            session.homework = coach_notebook.save_update(db, nb_row, result.get("notebook"))
        except Exception as e:
            db.rollback()
            print(f"[career-coach] Notebook update failed for user {user.id}: {e}")
            session.status = "completed"
    db.commit()
    db.refresh(session)
    rise_index.award_points(db, user, "career_coach_session_completed", "Completed a Career Coach session")
    # Optional Discord follow-up (no-op unless they've connected Discord).
    background_tasks.add_task(discord_notify.send_session_followup, session.id)
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


@router.get("/videos", response_model=schemas.CoachVideosOut)
def coach_videos(
    q: str = Query(..., min_length=2, max_length=100),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Real, embeddable YouTube videos for a topic, found by search (the model
    never names videos). Always returns a link to the YouTube search too, so it
    works with no API key and when the monthly in-app allowance is used up.
    Cached results are free; only a fresh YouTube search is metered."""
    query = videos_service.normalize(q)
    if len(query) < 2:
        raise HTTPException(status_code=422, detail="Say what you want a video about.")
    out = {"query": query, "videos": [], "search_url": videos_service.search_url(query), "note": ""}
    if not videos_service.enabled():
        return out
    found = videos_service.cached(db, query)
    if found is None:
        try:
            usage.check_and_increment(db, user, "coach_video", 1)
        except HTTPException:
            out["note"] = "You've used this month's in-app videos. The YouTube link still works."
            return out
        try:
            found = videos_service.fetch(query)
        except Exception as e:
            usage.decrement(db, user.id, "coach_video", 1)
            print(f"[videos] YouTube search failed for {query!r}: {e}")
            out["note"] = "Couldn't load videos just now. The YouTube link still works."
            return out
        videos_service.save(db, query, found)
    out["videos"] = found
    if not found:
        out["note"] = "No embeddable videos found for that. Try the YouTube link or different words."
    return out


# --- What the coach remembers (see services/coach_notebook.py) -----------
def _notebook_out(row: models.CoachNotebook) -> schemas.CoachNotebookOut:
    return schemas.CoachNotebookOut(enabled=bool(row.enabled), items=coach_notebook.items_of(row))


@router.get("/notebook", response_model=schemas.CoachNotebookOut)
def get_notebook(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _notebook_out(coach_notebook.get_row(db, user.id))


@router.put("/notebook", response_model=schemas.CoachNotebookOut)
def set_notebook(payload: schemas.CoachNotebookSettings, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    row = coach_notebook.get_row(db, user.id)
    row.enabled = payload.enabled
    db.commit()
    return _notebook_out(row)


@router.delete("/notebook/{item_id}", response_model=schemas.CoachNotebookOut)
def delete_notebook_item(item_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = coach_notebook.get_row(db, user.id)
    row.items = json.dumps([i for i in coach_notebook.items_of(row) if i["id"] != item_id])
    db.commit()
    return _notebook_out(row)


@router.delete("/notebook", response_model=schemas.CoachNotebookOut)
def clear_notebook(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = coach_notebook.get_row(db, user.id)
    row.items = "[]"
    db.commit()
    return _notebook_out(row)
