"""If GitHub's hourly trigger is not heard from, the server sends the hour's alerts itself."""
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import models
from app.database import Base, SessionLocal, engine
from app.main import app
from app.services import alert_status, alert_timer, pipeline_runner

TestClient(app)
Base.metadata.create_all(bind=engine)

AT = datetime(2026, 11, 16, 14, 30)          # half past the hour


def _clear(db):
    db.query(models.ScheduledRunLog).filter_by(run_type=alert_status.HEARTBEAT).delete()
    db.commit()


def test_runs_when_nothing_has_been_heard_from_the_trigger():
    db = SessionLocal()
    try:
        _clear(db)
        assert alert_timer.should_run(db, AT)
    finally:
        db.close()


def test_waits_until_after_the_github_trigger_has_had_its_turn():
    db = SessionLocal()
    try:
        _clear(db)
        assert not alert_timer.should_run(db, AT.replace(minute=10))
        assert alert_timer.should_run(db, AT.replace(minute=20))
    finally:
        db.close()


def test_stays_quiet_when_the_trigger_is_working():
    db = SessionLocal()
    try:
        _clear(db)
        alert_status.record_tick(db, {}, AT - timedelta(minutes=25))      # GitHub's run at :05
        assert not alert_timer.should_run(db, AT)
        assert alert_timer.should_run(db, AT + timedelta(minutes=50))     # 15:20, an hour later, nothing new
    finally:
        db.close()


def test_failed_runs_do_not_count_as_the_job_running():
    db = SessionLocal()
    try:
        _clear(db)
        alert_status.record_tick(db, {}, AT - timedelta(minutes=25), error="boom")
        assert alert_timer.should_run(db, AT)
    finally:
        db.close()


def test_run_once_sends_once_and_marks_the_hour_taken():
    db = SessionLocal()
    try:
        _clear(db)
        with patch.object(pipeline_runner, "send_smart_alerts", return_value={"digests_sent": 0, "quiet_notes": 0}) as send:
            assert alert_timer.run_once(AT) is True
            assert alert_timer.run_once(AT + timedelta(minutes=5)) is False      # the next look, five minutes on
        assert send.call_count == 1
        tick = db.query(models.ScheduledRunLog).filter_by(run_type=alert_status.HEARTBEAT).first()
        assert tick.status == "success" and "server timer" in tick.result_json
    finally:
        db.close()


def test_a_crash_is_recorded_and_the_timer_survives():
    db = SessionLocal()
    try:
        _clear(db)
        with patch.object(pipeline_runner, "send_smart_alerts", side_effect=RuntimeError("no network")):
            assert alert_timer.run_once(AT) is True
        db.expire_all()
        failed = db.query(models.ScheduledRunLog).filter_by(run_type=alert_status.HEARTBEAT, status="failed").first()
        assert failed and "no network" in failed.error
    finally:
        db.close()
