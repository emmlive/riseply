"""
Spaced-repetition delivery for org onboarding micro-lessons (the
"Culture Bot").

Deliberately simple: no vector search, no LLM grading. Lessons are
short, admin-authored content strings delivered by email on a schedule
relative to when the employee's org-linked application record was
created (their join date), with an optional plain-text quiz graded by
case-insensitive substring match. This is the same "coarse but honest"
choice made in safety_flags.py: cheap, deterministic, and it doesn't
pretend to have capabilities -- Slack/Teams delivery, semantic quiz
grading -- that aren't actually wired up in this codebase yet. Email is
the one delivery channel that's real today.

Meant to be triggered once a day by an external scheduler hitting
POST /orgs/culture-bot/run, the same pattern pipeline_runner.run_discovery
uses for job discovery.
"""
from datetime import datetime, date
from sqlalchemy.orm import Session

from app import models
from app.services import notifier

REMINDER_AFTER_DAYS = 7


def run_deliveries(db: Session) -> dict:
    """Finds every org-linked application whose days-since-join matches
    a lesson's day_offset today and hasn't been delivered yet, sends it,
    and records the delivery. Also resends a reminder for any quiz
    answered incorrectly a week ago that hasn't been reminded yet.

    Idempotent by design: the unique (application_id, lesson_id)
    constraint on LessonDelivery means calling this twice in a day (a
    retry, a manual re-run) never double-sends -- each lesson is checked
    against existing deliveries before anything goes out."""
    sent = 0
    reminders = 0

    apps = db.query(models.Application).filter(models.Application.organization_id.isnot(None)).all()

    for app_row in apps:
        days_since_join = (date.today() - app_row.created_at.date()).days

        lessons_q = db.query(models.OrgLesson).filter_by(
            organization_id=app_row.organization_id, day_offset=days_since_join
        )
        if app_row.department_id:
            lessons_q = lessons_q.filter(
                (models.OrgLesson.department_id.is_(None))
                | (models.OrgLesson.department_id == app_row.department_id)
            )
        else:
            lessons_q = lessons_q.filter(models.OrgLesson.department_id.is_(None))

        for lesson in lessons_q.all():
            already = db.query(models.LessonDelivery).filter_by(
                application_id=app_row.id, lesson_id=lesson.id
            ).first()
            if already:
                continue

            user = db.query(models.User).filter_by(id=app_row.user_id).first()
            if not user:
                continue

            body = lesson.content
            if lesson.quiz_question:
                body += (
                    f"\n\nQuick check: {lesson.quiz_question}\n"
                    "Answer it from your onboarding checklist in the app -- "
                    "this lesson will be waiting there."
                )
            try:
                notifier.send_email(
                    user.notify_email or user.email, f"Day {lesson.day_offset}: {lesson.title}", body,
                )
            except Exception:
                continue

            db.add(models.LessonDelivery(application_id=app_row.id, lesson_id=lesson.id))
            db.commit()
            sent += 1

        due_reminders = db.query(models.LessonDelivery).filter(
            models.LessonDelivery.application_id == app_row.id,
            models.LessonDelivery.quiz_correct.is_(False),
            models.LessonDelivery.reminder_sent_at.is_(None),
        ).all()
        for delivery in due_reminders:
            if (datetime.utcnow() - delivery.delivered_at).days < REMINDER_AFTER_DAYS:
                continue
            lesson = db.query(models.OrgLesson).filter_by(id=delivery.lesson_id).first()
            user = db.query(models.User).filter_by(id=app_row.user_id).first()
            if not lesson or not user:
                continue
            try:
                notifier.send_email(
                    user.notify_email or user.email,
                    f"Reminder: {lesson.title}",
                    f"Quick refresher, since this one tripped you up before:\n\n{lesson.content}",
                )
            except Exception:
                continue
            delivery.reminder_sent_at = datetime.utcnow()
            db.commit()
            reminders += 1

    return {"lessons_sent": sent, "culture_bot_reminders_sent": reminders}


def grade_quiz(quiz_answer: str, response: str) -> bool:
    """Case-insensitive substring match -- deliberately not exact-match
    (so 'expense reports' still matches an expected answer of 'expense
    report'), and deliberately not an LLM call (a wrong-vs-right call on
    a short factual quiz answer doesn't need one, and a human should be
    able to see exactly why something was marked correct or not)."""
    if not quiz_answer.strip():
        return True  # no quiz configured -- nothing to get wrong
    return quiz_answer.strip().lower() in response.strip().lower()
