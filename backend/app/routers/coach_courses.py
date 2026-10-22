import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import syllabus, usage

# Career Coach courses: a syllabus the coach teaches module by module, one
# coach session per module (CareerCoachSession.course_id/module_id), with an
# end-of-module recap. Building a syllabus is metered ("course"); the lessons
# themselves are ordinary coach messages and meter as such.
router = APIRouter(prefix="/career-coach/courses", tags=["career-coach"])

ACTION = "course"
MAX_COURSES = 30


def _loads(text: str, default):
    try:
        v = json.loads(text or "")
    except Exception:
        return default
    return v if isinstance(v, type(default)) else default


def course_data(course: models.CoachCourse) -> dict:
    return _loads(course.data, {})


def done_ids(course: models.CoachCourse) -> list[str]:
    return [str(x) for x in _loads(course.done, [])]


def get_owned(db: Session, course_id: int, user_id: int) -> models.CoachCourse:
    c = db.query(models.CoachCourse).filter_by(id=course_id, user_id=user_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Course not found")
    return c


def mark_done(db: Session, course: models.CoachCourse, module_id: str) -> None:
    ids = done_ids(course)
    if module_id and module_id not in ids:
        course.done = json.dumps(ids + [module_id])
        db.commit()


def ensure_recap(db: Session, session: models.CareerCoachSession, user: models.User, history: list[dict]) -> dict | None:
    """Build and store the module recap once. Never raises: a missing recap
    can be rebuilt later from the recap endpoint, and must not break a lesson."""
    if session.recap:
        return _loads(session.recap, {}) or None
    if not session.course_id or not session.module_id:
        return None
    course = db.query(models.CoachCourse).filter_by(id=session.course_id, user_id=user.id).first()
    if not course:
        return None
    try:
        recap = syllabus.make_recap(session.target_role, course_data(course), session.module_id, history)
    except Exception as e:
        print(f"[coach-course] Recap failed for session {session.id}: {e}")
        return None
    session.recap = json.dumps(recap)
    db.commit()
    mark_done(db, course, session.module_id)
    return recap


def _course_out(db: Session, course: models.CoachCourse) -> schemas.CoachCourseOut:
    data = course_data(course)
    done = set(done_ids(course))
    sessions = db.query(models.CareerCoachSession).filter_by(user_id=course.user_id, course_id=course.id).order_by(
        models.CareerCoachSession.id.asc()).all()
    latest = {s.module_id: s for s in sessions}  # later sessions overwrite earlier ones
    mods = []
    for m in data.get("modules", []):
        s = latest.get(m["id"])
        mods.append(schemas.CoachModuleOut(
            **m, done=m["id"] in done, session_id=s.id if s else None,
            session_status=s.status if s else "", recap_ready=bool(s and s.recap),
        ))
    return schemas.CoachCourseOut(
        id=course.id, target_role=course.target_role, title=data.get("title") or course.title,
        overview=data.get("overview", ""), outcomes=data.get("outcomes", []),
        prerequisites=data.get("prerequisites", []), total_hours=data.get("total_hours", 0),
        created_at=course.created_at, modules=mods, done=sum(1 for m in mods if m.done),
    )


@router.post("", response_model=schemas.CoachCourseOut, status_code=201)
def create_course(payload: schemas.CoachCourseRequest, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    if not (user.resume_text or "").strip():
        raise HTTPException(status_code=400, detail="Add your resume before building a course.")
    if db.query(models.CoachCourse).filter_by(user_id=user.id).count() >= MAX_COURSES:
        raise HTTPException(status_code=400, detail=f"You can keep up to {MAX_COURSES} courses. Delete one you no longer need.")
    role = payload.target_role.strip()
    topic = payload.topic.strip()
    # Reuse an existing course for the same role and topic instead of paying for another syllabus.
    for c in db.query(models.CoachCourse).filter_by(user_id=user.id, target_role=role, topic=topic).all():
        return _course_out(db, c)

    usage.check_and_increment(db, user, ACTION, 1)
    try:
        data = syllabus.build(role, topic, [s.strip() for s in payload.skills if s.strip()], user.resume_text)
    except Exception as e:
        usage.decrement(db, user.id, ACTION, 1)
        print(f"[coach-course] Syllabus failed for user {user.id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Couldn't build the course right now — this attempt wasn't counted against your limit. Try again shortly.",
        )
    course = models.CoachCourse(user_id=user.id, target_role=role, topic=topic, title=data["title"], data=json.dumps(data))
    db.add(course)
    db.commit()
    db.refresh(course)
    return _course_out(db, course)


@router.get("", response_model=list[schemas.CoachCourseListItem])
def list_courses(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = db.query(models.CoachCourse).filter_by(user_id=user.id).order_by(models.CoachCourse.id.desc()).all()
    return [schemas.CoachCourseListItem(
        id=c.id, title=c.title, target_role=c.target_role, created_at=c.created_at,
        modules=len(course_data(c).get("modules", [])), done=len(done_ids(c)),
    ) for c in rows]


@router.get("/{course_id}", response_model=schemas.CoachCourseOut)
def get_course(course_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _course_out(db, get_owned(db, course_id, user.id))


@router.delete("/{course_id}", status_code=204)
def delete_course(course_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    course = get_owned(db, course_id, user.id)
    # Lessons already taught stay in the person's session history.
    db.query(models.CareerCoachSession).filter_by(user_id=user.id, course_id=course.id).update({"course_id": None})
    db.delete(course)
    db.commit()


@router.post("/sessions/{session_id}/recap", response_model=dict)
def rebuild_recap(session_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Build the recap for a module session when it wasn't made automatically
    (the model call failed, or the person wants it before every objective is ticked)."""
    s = db.query(models.CareerCoachSession).filter_by(id=session_id, user_id=user.id).first()
    if not s or not s.course_id:
        raise HTTPException(status_code=404, detail="Module session not found")
    rows = db.query(models.CareerCoachMessage).filter_by(session_id=s.id, user_id=user.id).order_by(
        models.CareerCoachMessage.id.asc()).all()
    if len(rows) < 3:
        raise HTTPException(status_code=400, detail="Have a few exchanges with the coach first, then ask for the recap.")
    recap = ensure_recap(db, s, user, [{"role": m.role, "content": m.content} for m in rows])
    if not recap:
        raise HTTPException(status_code=502, detail="Couldn't build the recap right now. Try again shortly.")
    return recap


@router.post("/sessions/{session_id}/save-recap", response_model=schemas.StudyNoteOut, status_code=201)
def save_recap(session_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """File the module recap in a study folder named after the course (created
    on first use). Saving twice replaces the earlier copy instead of duplicating it."""
    s = db.query(models.CareerCoachSession).filter_by(id=session_id, user_id=user.id).first()
    recap = _loads(s.recap, {}) if s else {}
    if not s or not s.course_id or not recap:
        raise HTTPException(status_code=404, detail="No recap to save yet.")
    course = get_owned(db, s.course_id, user.id)
    data = course_data(course)
    title, content = syllabus.recap_note(data, s.module_id, recap)
    folder = db.get(models.StudyFolder, course.folder_id) if course.folder_id else None
    if not folder or folder.user_id != user.id:
        name = f"Course: {data.get('title') or course.title}"[:80]
        folder = db.query(models.StudyFolder).filter(
            models.StudyFolder.user_id == user.id, models.StudyFolder.name.ilike(name)).first()
        if not folder:
            folder = models.StudyFolder(user_id=user.id, name=name)
            db.add(folder)
            db.flush()
        course.folder_id = folder.id
    note = db.query(models.StudyNote).filter_by(
        user_id=user.id, folder_id=folder.id, session_id=s.id, source="recap").first()
    label = f"Course · {data.get('title') or course.title}"[:160]
    if note:
        note.title, note.content, note.source_label = title, content, label
    else:
        note = models.StudyNote(user_id=user.id, folder_id=folder.id, session_id=s.id, title=title,
                                content=content, source="recap", source_label=label)
        db.add(note)
    db.commit()
    db.refresh(note)
    return note
