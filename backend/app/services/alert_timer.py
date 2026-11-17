"""The hourly smart-alert run, with a safety net.

The normal trigger is the "Smart alerts" GitHub Actions workflow, which calls
/internal/send-alerts at five past each hour. GitHub's scheduler is not
something this app can see or fix, and when it does not fire nobody gets a
digest and nothing says so. So the server also checks its own clock: if no
successful run has been recorded in the last 50 minutes, it sends the hourly
alerts itself, from twenty past the hour, which leaves GitHub's trigger first
go. Either way the work is the same function, a person gets at most one digest
a day, and each run leaves the same record the health card reads."""
import threading
import time
from datetime import datetime, timedelta

from app.config import settings
from app.database import SessionLocal
from app import models

CHECK_EVERY = 300                       # seconds between looks at the clock
FIRST_LOOK_AFTER = 90                   # seconds after boot, so startup work finishes first
RUN_AFTER_MINUTE = 20                   # leaves 15 minutes for the GitHub trigger to go first
MAX_GAP = timedelta(minutes=50)


def should_run(db, now: datetime) -> bool:
    if now.minute < RUN_AFTER_MINUTE:
        return False
    from app.services import alert_status
    last_ok = db.query(models.ScheduledRunLog.started_at).filter(
        models.ScheduledRunLog.run_type == alert_status.HEARTBEAT, models.ScheduledRunLog.status == "success"
    ).order_by(models.ScheduledRunLog.started_at.desc()).first()
    return last_ok is None or now - last_ok[0] > MAX_GAP


def run_once(now: datetime | None = None) -> bool:
    """One look at the clock. True when it sent the hour's alerts."""
    from app.services import alert_status, pipeline_runner
    now = now or datetime.utcnow()
    db = SessionLocal()
    try:
        if not should_run(db, now):
            return False
        # Written first, so a second look (or the GitHub trigger) sees this hour is taken.
        alert_status.record_tick(db, {"by": "server timer"}, now)
        try:
            pipeline_runner.send_smart_alerts(db, now)
        except Exception as e:
            db.rollback()
            alert_status.record_tick(db, {}, now, error=f"{type(e).__name__}: {e}")
            print(f"[alert-timer] smart alerts failed: {type(e).__name__}: {e}")
        return True
    finally:
        db.close()


def _loop() -> None:
    time.sleep(FIRST_LOOK_AFTER)
    while True:
        try:
            run_once()
        except Exception as e:           # never let the timer die
            print(f"[alert-timer] {type(e).__name__}: {e}")
        time.sleep(CHECK_EVERY)


def start() -> None:
    if not settings.alerts_timer_enabled:
        return
    threading.Thread(target=_loop, name="alert-timer", daemon=True).start()
