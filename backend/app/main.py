from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.exc import OperationalError
from starlette.responses import JSONResponse

from app.database import Base, engine, SessionLocal
from app.config import settings
from app.migrate import run_migration
from app.kb_seed import seed_kb_if_empty
from app.library_seed import seed_library_if_empty
from app.rate_limit import limiter
from app.routers import auth, me, profiles, pipeline, billing, interview, job_buddy, rise_index, support, admin, internal, org_buddy, kb, extension, resumes, sso, bookmarklet, calendar, career_coach, library, discounts, discord, study, progress, feedback, skill_gap, fit_score, networking, company_brief

def _fail_orphaned_match_runs() -> None:
    """Interactive searches run inside this web process, so any still
    marked "running" when the process starts belong to a previous
    process (a deploy or a memory restart) and can never finish. Mark
    them failed right away, so nobody is stuck behind a dead run."""
    from datetime import datetime
    from app import models

    db = SessionLocal()
    try:
        db.query(models.ScheduledRunLog).filter(
            models.ScheduledRunLog.run_type == "interactive_match",
            models.ScheduledRunLog.status == "running",
        ).update({
            "status": "failed",
            "error": "This search was interrupted (the server restarted while it was running). Please try again.",
            "finished_at": datetime.utcnow(),
        }, synchronize_session=False)
        db.commit()
    except Exception as e:  # never block startup on housekeeping
        db.rollback()
        print(f"[startup] couldn't clear orphaned match runs: {e}")
    finally:
        db.close()


def _run_startup_tasks() -> None:
    """Everything the app does once at boot, in order.

    - run_migration() adds any columns/tables that are new in the code but
      missing from the live database, so every deploy self-heals instead of
      needing a manual migration step (see app/migrate.py).
    - The seeds are one-time (idempotent) starter content, so the knowledge
      base and library are useful immediately rather than empty.
    - Then any search left "running" by a previous process is failed.

    All of it is safe to run again, which is what lets a boot that happened
    while the database was unreachable try again later."""
    run_migration()
    _seed_db = SessionLocal()
    try:
        seed_kb_if_empty(_seed_db)
        seed_library_if_empty(_seed_db)
    finally:
        _seed_db.close()
    _fail_orphaned_match_runs()


STARTUP_RETRY_SECONDS = 30
STARTUP_RETRY_ATTEMPTS = 120  # about an hour


def _retry_startup_in_background() -> None:
    import threading
    import time

    def loop():
        for attempt in range(1, STARTUP_RETRY_ATTEMPTS + 1):
            time.sleep(STARTUP_RETRY_SECONDS)
            try:
                _run_startup_tasks()
                print(f"[startup] database reachable again; startup tasks done (retry {attempt})")
                return
            except Exception as e:
                print(f"[startup] retry {attempt} failed: {type(e).__name__}")
        print("[startup] gave up retrying startup tasks")

    threading.Thread(target=loop, name="startup-retry", daemon=True).start()


# A database that is down or over its quota used to crash the whole boot
# ("Exited with status 1"), so Render restarted it over and over and every
# scheduled job failed. Now the app comes up anyway: requests get a clear
# 503 until the database answers, and the startup tasks run again by
# themselves once it does.
try:
    _run_startup_tasks()
except OperationalError as e:
    print(f"[startup] database unreachable, starting anyway and retrying: {type(e).__name__}")
    _retry_startup_in_background()

app = FastAPI(title="Riseply API")

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests — please wait a bit and try again."},
    )


@app.exception_handler(OperationalError)
def database_unavailable_handler(request, exc):
    """The database refused or dropped the connection (down, restarting, or
    over its plan's limits). 503 + Retry-After tells browsers and the
    scheduled jobs this is temporary, instead of a generic 500."""
    return JSONResponse(
        status_code=503,
        headers={"Retry-After": "30"},
        content={"detail": "Riseply can't reach its database right now. Please try again in a minute."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(me.router)
app.include_router(profiles.router)
app.include_router(pipeline.router)
app.include_router(billing.router)
app.include_router(interview.router)
app.include_router(job_buddy.router)
app.include_router(career_coach.router)
app.include_router(skill_gap.router)
app.include_router(fit_score.router)
app.include_router(networking.router)
app.include_router(company_brief.router)
app.include_router(study.router)
app.include_router(progress.router)
app.include_router(feedback.router)
app.include_router(feedback.admin_router)
app.include_router(library.router)
app.include_router(discounts.router)
app.include_router(discord.router)
app.include_router(rise_index.router)
app.include_router(support.router)
app.include_router(admin.router)
app.include_router(internal.router)
app.include_router(org_buddy.router)
app.include_router(kb.router)
app.include_router(extension.router)
app.include_router(resumes.router)
app.include_router(sso.router)
app.include_router(bookmarklet.router)
app.include_router(calendar.router)

# Tailored resumes are now served from Postgres via
# GET /applications/{id}/tailored-resume (see routers/pipeline.py) --
# not from this local disk mount, which vanished on every redeploy
# since Render's web service filesystem is ephemeral. Left unmounted
# intentionally rather than kept as dead infrastructure.


@app.get("/health")
def health():
    return {"status": "ok"}
