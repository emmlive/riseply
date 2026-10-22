import json
import random
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import exam_prep, usage

# Exam prep: study for a certification or board exam. Planning (the outline) and
# generating questions are metered; grading and spaced review cost nothing.
router = APIRouter(prefix="/exams", tags=["exams"])

MAX_EXAMS = 15
PER_DOMAIN_GEN = 10
NOTE = ("This outline and these questions are AI-written study aids, not official exam content. "
        "Check domains and weights against the exam provider's own outline, and check any answer you doubt.")


def _loads(text, default):
    try:
        v = json.loads(text or "")
    except Exception:
        return default
    return v if isinstance(v, type(default)) else default


def get_owned(db: Session, exam_id: int, user_id: int) -> models.ExamPrep:
    e = db.query(models.ExamPrep).filter_by(id=exam_id, user_id=user_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Exam not found")
    return e


def _outline(e) -> dict:
    return _loads(e.outline, {})


def _domain(e, domain_id: str) -> dict:
    for d in _outline(e).get("domains", []):
        if d["id"] == domain_id:
            return d
    raise HTTPException(status_code=404, detail="Domain not found")


def _q_out(q: models.ExamQuestion, reveal: bool) -> dict:
    d = {"id": q.id, "domain_id": q.domain_id, "topic": q.topic, "stem": q.stem, "options": _loads(q.options, [])}
    if reveal:
        d["correct"] = q.correct
        d["explanation"] = q.explanation
    return d


def weak_topics(qs: list, domain_id: str, limit: int = 6) -> list[str]:
    """Topics of the questions the person has missed in a domain, most missed first."""
    counts: dict = {}
    for q in qs:
        if q.domain_id == domain_id and (q.times_wrong or 0) > 0 and q.topic:
            counts[q.topic] = counts.get(q.topic, 0) + q.times_wrong
    return [t for t, _ in sorted(counts.items(), key=lambda x: -x[1])][:limit]


def exam_view(db: Session, e: models.ExamPrep) -> dict:
    o = _outline(e)
    now = datetime.utcnow()
    qs = db.query(models.ExamQuestion).filter_by(exam_id=e.id).all()
    doms = []
    for d in o.get("domains", []):
        mine = [q for q in qs if q.domain_id == d["id"]]
        seen = sum(q.times_seen for q in mine)
        wrong = sum(q.times_wrong for q in mine)
        doms.append({**d, "questions": len(mine), "answered": seen,
                     "accuracy": round(100 * (seen - wrong) / seen) if seen else None,
                     "due": sum(1 for q in mine if q.due_at and q.due_at <= now),
                     "weak_topics": weak_topics(qs, d["id"])})
    sched = exam_prep.build_schedule(doms, e.exam_date, e.hours_per_week or 0) if e.exam_date else None
    return {"exam_date": e.exam_date or "", "hours_per_week": e.hours_per_week or 0, "schedule": sched, "id": e.id, "exam_name": e.exam_name, "name": o.get("name") or e.exam_name, "body": o.get("body", ""),
            "confidence": o.get("confidence", "medium"), "summary": o.get("summary", ""), "domains": doms,
            "due": sum(d["due"] for d in doms), "note": NOTE, "created_at": e.created_at}


def _generate(db, user, e, domain: dict, count: int) -> list[models.ExamQuestion]:
    """One metered model call; stores and returns new questions."""
    usage.check_and_increment(db, user, "exam_questions")
    avoid = [q.stem for q in db.query(models.ExamQuestion).filter_by(exam_id=e.id, domain_id=domain["id"]).all()]
    try:
        items = exam_prep.questions(e.exam_name, domain, count, avoid)
    except Exception:
        usage.decrement(db, user.id, "exam_questions", 1)
        raise HTTPException(status_code=502, detail="Couldn't write questions just now. Your allowance wasn't used. Try again.")
    out = []
    for it in items:
        q = models.ExamQuestion(exam_id=e.id, user_id=user.id, domain_id=domain["id"], topic=it["topic"], stem=it["stem"],
                                options=json.dumps(it["options"]), correct=it["correct"], explanation=it["explanation"])
        db.add(q)
        out.append(q)
    db.commit()
    return out


def _start(db, e, user, kind, qs, domain_id="", minutes=0) -> dict:
    random.shuffle(qs)
    a = models.ExamAttempt(exam_id=e.id, user_id=user.id, kind=kind, domain_id=domain_id,
                           question_ids=json.dumps([q.id for q in qs]), time_limit_min=minutes)
    db.add(a)
    db.commit()
    return {"attempt_id": a.id, "kind": kind, "time_limit_min": minutes, "questions": [_q_out(q, False) for q in qs]}


def _record(db, q: models.ExamQuestion, choice: int) -> bool:
    ok = choice == q.correct
    q.times_seen = (q.times_seen or 0) + 1
    if not ok:
        q.times_wrong = (q.times_wrong or 0) + 1
    q.box, q.due_at = exam_prep.next_due(q.box or 0, ok)
    return ok


@router.post("")
def create_exam(body: schemas.ExamCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if db.query(models.ExamPrep).filter_by(user_id=user.id).count() >= MAX_EXAMS:
        raise HTTPException(status_code=400, detail="You have the maximum number of exams. Delete one to add another.")
    usage.check_and_increment(db, user, "exam_plan")
    try:
        o = exam_prep.outline(body.exam_name.strip())
    except Exception:
        usage.decrement(db, user.id, "exam_plan", 1)
        raise HTTPException(status_code=502, detail="Couldn't build the outline just now. Your allowance wasn't used. Try again.")
    e = models.ExamPrep(user_id=user.id, exam_name=body.exam_name.strip(), outline=json.dumps(o))
    db.add(e)
    db.commit()
    db.refresh(e)
    return exam_view(db, e)


@router.get("")
def list_exams(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = db.query(models.ExamPrep).filter_by(user_id=user.id).order_by(models.ExamPrep.id.desc()).all()
    return [{"id": e.id, "exam_name": e.exam_name, "created_at": e.created_at} for e in rows]


@router.get("/{exam_id}")
def get_exam(exam_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return exam_view(db, get_owned(db, exam_id, user.id))


@router.delete("/{exam_id}")
def delete_exam(exam_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    e = get_owned(db, exam_id, user.id)
    db.query(models.ExamQuestion).filter_by(exam_id=e.id).delete()
    db.query(models.ExamAttempt).filter_by(exam_id=e.id).delete()
    db.delete(e)
    db.commit()
    return {"ok": True}


@router.put("/{exam_id}/schedule")
def set_schedule(exam_id: int, body: schemas.ExamScheduleRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    e = get_owned(db, exam_id, user.id)
    if body.exam_date:
        try:
            datetime.strptime(body.exam_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Use a date like 2026-12-15")
    e.exam_date = body.exam_date
    e.hours_per_week = body.hours_per_week
    db.commit()
    return exam_view(db, e)


@router.post("/{exam_id}/practice")
def practice(exam_id: int, body: schemas.ExamPracticeRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    e = get_owned(db, exam_id, user.id)
    d = _domain(e, body.domain_id)
    qs = _generate(db, user, e, d, body.count)
    return _start(db, e, user, "practice", qs, d["id"])


@router.post("/{exam_id}/mock")
def mock(exam_id: int, body: schemas.ExamMockRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    e = get_owned(db, exam_id, user.id)
    doms = _outline(e).get("domains", [])
    if not doms:
        raise HTTPException(status_code=400, detail="This exam has no domains")
    # Questions per domain follow the domain weights (at least one each).
    want = {d["id"]: max(1, round(body.count * d["weight_pct"] / 100)) for d in doms}
    picked: list[models.ExamQuestion] = []
    for d in doms:
        pool = db.query(models.ExamQuestion).filter_by(exam_id=e.id, domain_id=d["id"]).all()
        # Unanswered and least-seen first, so a mock mostly shows fresh questions.
        pool.sort(key=lambda q: (q.times_seen or 0, random.random()))
        picked += pool[:want[d["id"]]]
        short = want[d["id"]] - len(pool[:want[d["id"]]])
        while short > 0:
            batch = min(short, PER_DOMAIN_GEN)
            new = _generate(db, user, e, d, batch)
            picked += new
            short -= max(len(new), 1)
    minutes = body.minutes or round(len(picked) * 1.5)
    return _start(db, e, user, "mock", picked[:body.count + len(doms)], "", minutes)


@router.post("/{exam_id}/review")
def review(exam_id: int, body: schemas.ExamReviewRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    e = get_owned(db, exam_id, user.id)
    due = (db.query(models.ExamQuestion)
           .filter(models.ExamQuestion.exam_id == e.id, models.ExamQuestion.due_at != None,  # noqa: E711
                   models.ExamQuestion.due_at <= datetime.utcnow())
           .order_by(models.ExamQuestion.due_at).limit(body.count).all())
    if not due:
        raise HTTPException(status_code=400, detail="Nothing is due for review yet. Answer some practice questions first.")
    return _start(db, e, user, "review", due)


def _attempt(db, attempt_id, user_id) -> models.ExamAttempt:
    a = db.query(models.ExamAttempt).filter_by(id=attempt_id, user_id=user_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Attempt not found")
    return a


@router.post("/attempts/{attempt_id}/answer")
def answer(attempt_id: int, body: schemas.ExamAnswerIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Practice and review: grade one answer now and show why."""
    a = _attempt(db, attempt_id, user.id)
    if a.kind == "mock":
        raise HTTPException(status_code=400, detail="Mock exam answers are graded when you finish")
    ans = _loads(a.answers, {})
    if body.question_id not in _loads(a.question_ids, []):
        raise HTTPException(status_code=404, detail="Question not in this attempt")
    q = db.query(models.ExamQuestion).filter_by(id=body.question_id, user_id=user.id).first()
    if str(q.id) in ans:
        return {"correct": ans[str(q.id)] == q.correct, "correct_index": q.correct, "explanation": q.explanation}
    ok = _record(db, q, body.choice)
    ans[str(q.id)] = body.choice
    a.answers = json.dumps(ans)
    db.commit()
    return {"correct": ok, "correct_index": q.correct, "explanation": q.explanation}


@router.post("/attempts/{attempt_id}/finish")
def finish(attempt_id: int, body: schemas.ExamFinishRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    a = _attempt(db, attempt_id, user.id)
    e = get_owned(db, a.exam_id, user.id)
    ids = _loads(a.question_ids, [])
    ans = _loads(a.answers, {})
    if a.status != "finished":
        if a.kind == "mock":
            for x in body.answers:
                if x.question_id in ids and str(x.question_id) not in ans:
                    q = db.query(models.ExamQuestion).filter_by(id=x.question_id, user_id=user.id).first()
                    _record(db, q, x.choice)
                    ans[str(q.id)] = x.choice
        qs = {q.id: q for q in db.query(models.ExamQuestion).filter(models.ExamQuestion.id.in_(ids)).all()}
        by: dict = {}
        right = 0
        for qid in ids:
            q = qs[qid]
            row = by.setdefault(q.domain_id, {"correct": 0, "total": 0})
            row["total"] += 1
            if ans.get(str(qid)) == q.correct:
                row["correct"] += 1
                right += 1
        a.answers = json.dumps(ans)
        a.by_domain = json.dumps(by)
        a.score = round(100 * right / len(ids)) if ids else 0
        a.status = "finished"
        a.finished_at = datetime.utcnow()
        db.commit()
    by = _loads(a.by_domain, {})
    ans = _loads(a.answers, {})
    names = {d["id"]: d["name"] for d in _outline(e).get("domains", [])}
    all_qs = db.query(models.ExamQuestion).filter_by(exam_id=e.id).all()
    qs = {q.id: q for q in db.query(models.ExamQuestion).filter(models.ExamQuestion.id.in_(ids)).all()}
    return {
        "score": a.score, "answered": len(ans), "total": len(ids),
        "domains": [{"id": k, "name": names.get(k, k), **v, "pct": round(100 * v["correct"] / v["total"])} for k, v in by.items()],
        "study_next": [{"id": k, "name": names.get(k, k), "weak_topics": weak_topics(all_qs, k)} for k in exam_prep.weak_domains(by)],
        "review": [{**_q_out(qs[i], True), "chosen": ans.get(str(i))} for i in ids],
        "note": NOTE,
    }
