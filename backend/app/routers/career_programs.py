import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.routers import coach_courses
from app.services import program, syllabus, usage

# Pivot programs: a bootcamp-style roadmap from zero to a job in a new field
# (services/program.py). Building the roadmap meters like a career path plan;
# each learning phase's course is built when the person reaches it and meters
# like any other course.
router = APIRouter(prefix="/career-programs", tags=["career-programs"])

MAX_PROGRAMS = 3


def _loads(text: str) -> dict:
    try:
        v = json.loads(text or "")
    except Exception:
        return {}
    return v if isinstance(v, dict) else {}


def _get(db: Session, program_id: int, user_id: int) -> models.CareerProgram:
    row = db.query(models.CareerProgram).filter_by(id=program_id, user_id=user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Program not found")
    return row


def _courses(db: Session, row: models.CareerProgram, state: dict) -> dict:
    """Phase id -> the course's progress, for phases whose course has been built."""
    out = {}
    for pid, cid in (state.get("courses") or {}).items():
        c = db.query(models.CoachCourse).filter_by(id=cid, user_id=row.user_id).first()
        if not c:
            continue
        done = set(coach_courses.done_ids(c))
        mods = [{"id": m["id"], "title": m["title"], "minutes": m.get("minutes", 45), "done": m["id"] in done}
                for m in coach_courses.course_data(c).get("modules", [])]
        out[pid] = {"id": c.id, "modules": mods, "total": len(mods), "done": sum(1 for m in mods if m["done"])}
    return out


def _out(db: Session, row: models.CareerProgram) -> schemas.ProgramOut:
    data, state = _loads(row.data), _loads(row.state)
    courses = _courses(db, row, state)
    phases = program.phase_states(data, state, courses)
    for p in phases:
        c = courses.get(p["id"])
        if c:
            p["modules"] = c["modules"]
    return schemas.ProgramOut(
        id=row.id, title=data.get("title", ""), target_role=row.target_role, overview=data.get("overview", ""),
        role_summary=data.get("role_summary", ""), honest_note=data.get("honest_note", ""),
        titles=data.get("titles", []), hours_per_week=row.hours_per_week,
        status=state.get("status") or "not_started", progress=program.overall_progress(phases),
        weeks_left=program.weeks_left(phases, courses, row.hours_per_week), phases=phases,
        next_step=program.next_step(phases, courses), week_plan=program.week_plan(phases, courses, row.hours_per_week),
        created_at=row.created_at,
    )


def _save_state(db: Session, row: models.CareerProgram, state: dict) -> None:
    row.state = json.dumps(state)
    db.commit()


@router.post("", response_model=schemas.ProgramOut, status_code=201)
def create_program(payload: schemas.ProgramCreate, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    role = payload.target_role.strip()
    rows = db.query(models.CareerProgram).filter_by(user_id=user.id).all()
    for r in rows:
        if r.target_role.lower() == role.lower():
            return _out(db, r)
    if len(rows) >= MAX_PROGRAMS:
        raise HTTPException(status_code=400, detail=f"You can keep up to {MAX_PROGRAMS} programs. Delete one you no longer need.")
    usage.check_and_increment(db, user, "career_path", 1)
    try:
        data = program.build(role, payload.hours_per_week, payload.background.strip(), user.resume_text or "")
    except Exception as e:
        usage.decrement(db, user.id, "career_path", 1)
        print(f"[program] Roadmap failed for user {user.id}: {e}")
        raise HTTPException(status_code=502, detail="Couldn't build your program right now. This attempt wasn't counted against your limit. Try again shortly.")
    row = models.CareerProgram(user_id=user.id, target_role=role, background=payload.background.strip(),
                               hours_per_week=payload.hours_per_week, data=json.dumps(data), state="{}")
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(db, row)


@router.get("", response_model=list[schemas.ProgramListItem])
def list_programs(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    out = []
    for r in db.query(models.CareerProgram).filter_by(user_id=user.id).order_by(models.CareerProgram.id.desc()).all():
        o = _out(db, r)
        out.append(schemas.ProgramListItem(id=r.id, title=o.title, target_role=r.target_role, progress=o.progress, created_at=r.created_at))
    return out


@router.get("/{program_id}", response_model=schemas.ProgramOut)
def get_program(program_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _out(db, _get(db, program_id, user.id))


@router.patch("/{program_id}", response_model=schemas.ProgramOut)
def patch_program(program_id: int, payload: schemas.ProgramPatch, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    row = _get(db, program_id, user.id)
    if payload.hours_per_week is not None:
        row.hours_per_week = payload.hours_per_week
    if payload.status is not None:
        state = _loads(row.state)
        state["status"] = payload.status
        row.state = json.dumps(state)
    db.commit()
    return _out(db, row)


@router.delete("/{program_id}", status_code=204)
def delete_program(program_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    db.delete(_get(db, program_id, user.id))
    db.commit()


@router.post("/{program_id}/phases/{phase_id}/course", response_model=schemas.ProgramOut)
def start_phase(program_id: int, phase_id: str, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    """Build the course for a learning phase once the person reaches it."""
    row = _get(db, program_id, user.id)
    data, state = _loads(row.data), _loads(row.state)
    phases = program.phase_states(data, state, _courses(db, row, state))
    phase = next((p for p in phases if p["id"] == phase_id), None)
    if not phase or phase["kind"] not in program.LEARNING:
        raise HTTPException(status_code=404, detail="Phase not found")
    if phase["status"] == "locked":
        raise HTTPException(status_code=400, detail="Finish the phase before this one first. Each one builds on the last.")
    if phase.get("course_id"):
        return _out(db, row)
    usage.check_and_increment(db, user, "course", 1)
    try:
        built = syllabus.build(row.target_role, phase["topic"], phase.get("skills", []), program.course_background(row.background))
    except Exception as e:
        usage.decrement(db, user.id, "course", 1)
        print(f"[program] Phase course failed for user {user.id}: {e}")
        raise HTTPException(status_code=502, detail="Couldn't build this phase right now. This attempt wasn't counted against your limit. Try again shortly.")
    course = models.CoachCourse(user_id=user.id, target_role=row.target_role, topic=phase["topic"],
                                title=built["title"], data=json.dumps(built))
    db.add(course)
    db.commit()
    db.refresh(course)
    state.setdefault("courses", {})[phase_id] = course.id
    _save_state(db, row, state)
    return _out(db, row)


def _items_len(row: models.CareerProgram, kind: str) -> int:
    for p in _loads(row.data).get("phases", []):
        if p["kind"] == kind:
            return len(p.get("items", []))
    return 0


@router.put("/{program_id}/projects/{index}", response_model=schemas.ProgramOut)
def set_project(program_id: int, index: int, payload: schemas.ProgramProjectIn, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    row = _get(db, program_id, user.id)
    if not 0 <= index < _items_len(row, "projects"):
        raise HTTPException(status_code=404, detail="Project not found")
    state = _loads(row.state)
    state.setdefault("projects", {})[str(index)] = {"done": payload.done, "url": payload.url.strip(), "note": payload.note.strip()}
    _save_state(db, row, state)
    return _out(db, row)


@router.put("/{program_id}/certs/{index}", response_model=schemas.ProgramOut)
def set_cert(program_id: int, index: int, payload: schemas.ProgramCertIn, db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)):
    row = _get(db, program_id, user.id)
    if not 0 <= index < _items_len(row, "certs"):
        raise HTTPException(status_code=404, detail="Certification not found")
    state = _loads(row.state)
    state.setdefault("certs", {})[str(index)] = payload.status
    _save_state(db, row, state)
    return _out(db, row)


@router.put("/{program_id}/checklist/{item_id}", response_model=schemas.ProgramOut)
def set_check(program_id: int, item_id: str, payload: schemas.ProgramCheckIn, db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user)):
    row = _get(db, program_id, user.id)
    ids = {it["id"] for p in _loads(row.data).get("phases", []) if p["kind"] == "job_ready" for it in p["items"]}
    if item_id not in ids:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    state = _loads(row.state)
    state.setdefault("checklist", {})[item_id] = payload.done
    _save_state(db, row, state)
    return _out(db, row)
