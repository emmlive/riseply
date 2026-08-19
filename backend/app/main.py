from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse

from app.database import Base, engine, SessionLocal
from app.config import settings
from app.migrate import run_migration
from app.kb_seed import seed_kb_if_empty
from app.rate_limit import limiter
from app.routers import auth, me, profiles, pipeline, billing, interview, job_buddy, rise_index, support, admin, internal, org_buddy, kb, extension, resumes, sso

# Adds any columns/tables that are new in the code but missing from the
# live database, so every deploy self-heals instead of needing a manual
# migration step. See app/migrate.py for exactly what this can and can't
# handle.
run_migration()

# One-time (idempotent) seed of real starter knowledge base content, so
# the KB is genuinely useful immediately rather than empty until an
# admin manually writes a dozen articles first.
_seed_db = SessionLocal()
try:
    seed_kb_if_empty(_seed_db)
finally:
    _seed_db.close()

app = FastAPI(title="Riseply API")

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests — please wait a bit and try again."},
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
app.include_router(rise_index.router)
app.include_router(support.router)
app.include_router(admin.router)
app.include_router(internal.router)
app.include_router(org_buddy.router)
app.include_router(kb.router)
app.include_router(extension.router)
app.include_router(resumes.router)
app.include_router(sso.router)

# Tailored resumes are now served from Postgres via
# GET /applications/{id}/tailored-resume (see routers/pipeline.py) --
# not from this local disk mount, which vanished on every redeploy
# since Render's web service filesystem is ephemeral. Left unmounted
# intentionally rather than kept as dead infrastructure.


@app.get("/health")
def health():
    return {"status": "ok"}
