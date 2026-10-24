"""A run left "running" by a dead process is failed at startup, so the daily job doesn't wait an hour."""
from app.database import SessionLocal
from app import models
from app.main import _fail_orphaned_match_runs


def test_dead_runs_are_failed_with_a_clear_reason_and_finished_ones_untouched():
    db = SessionLocal()
    rows = [models.ScheduledRunLog(run_type=t, status=s) for t, s in
            [("scheduled_run", "running"), ("interactive_discover", "running"), ("scheduled_run", "success")]]
    db.add_all(rows); db.commit()
    ids = [r.id for r in rows]
    _fail_orphaned_match_runs()
    db.expire_all()
    a, b, c = (db.get(models.ScheduledRunLog, i) for i in ids)
    assert a.status == "failed" and a.error.startswith("Interrupted") and a.finished_at is not None
    assert b.status == "failed" and "interrupted" in b.error
    assert c.status == "success" and not c.error
    db.close()
