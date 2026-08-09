import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

# Render (and formerly Heroku) hand out DATABASE_URL as `postgres://`, but
# SQLAlchemy 1.4+ requires the `postgresql://` scheme and raises on the
# old one. Rewrite it rather than let every deploy hit this silently.
database_url = settings.database_url
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# SQLite needs check_same_thread=False for use with FastAPI's threaded
# request handling; Postgres doesn't need or accept that argument.
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}

if database_url.startswith("sqlite"):
    db_path = database_url.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

engine = create_engine(
    database_url,
    connect_args=connect_args,
    # Neon (and managed/serverless Postgres generally) closes idle
    # connections server-side after a period of inactivity. Without
    # pool_pre_ping, SQLAlchemy's pool happily hands out a connection
    # object that looks fine to the pool but whose underlying socket is
    # already dead -- the first query on it crashes with exactly
    # "SSL connection has been closed unexpectedly" (a real production
    # incident, not hypothetical: this hit GET /me after an idle gap
    # during manual browser testing). pool_pre_ping issues a cheap
    # liveness check before handing out a pooled connection and
    # transparently reconnects if it's dead, at the cost of a small bit
    # of per-checkout latency. pool_recycle proactively retires
    # connections before they get old enough to hit this at all, as a
    # second line of defense for the same root cause.
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
