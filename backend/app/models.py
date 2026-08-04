from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date, Boolean, ForeignKey,
    UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, default="")
    phone = Column(String, default="")
    location = Column(String, default="")
    linkedin_url = Column(String, default="")
    portfolio_url = Column(String, default="")

    resume_text = Column(Text, default="")

    notify_email = Column(String, default="")  # defaults to account email if blank
    auto_submit = Column(Boolean, default=False)  # per-user override, defaults OFF

    created_at = Column(DateTime, default=datetime.utcnow)

    profiles = relationship("SearchProfile", back_populates="owner", cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="owner", cascade="all, delete-orphan")


class SearchProfile(Base):
    """One target-role profile per row. A user can have several running
    simultaneously — this is the multi-profile support from the CLI
    version, now editable in the UI instead of a config file."""
    __tablename__ = "search_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    name = Column(String, nullable=False)          # e.g. "AI Security Engineer"
    titles = Column(Text, default="[]")             # JSON list, stored as text
    locations = Column(Text, default="[]")
    seniority = Column(Text, default="[]")
    min_match_score = Column(Integer, default=70)
    exclude_companies = Column(Text, default="[]")
    keywords_required = Column(Text, default="[]")
    keywords_excluded = Column(Text, default="[]")
    active = Column(Boolean, default=True)

    owner = relationship("User", back_populates="profiles")


class Job(Base):
    """Discovered job postings — shared across all users (not per-tenant),
    since the same posting is relevant to anyone searching for it."""
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_external_id"),)

    id = Column(Integer, primary_key=True)
    source = Column(String, nullable=False)
    external_id = Column(String, nullable=False)
    company = Column(String, default="")
    title = Column(String, default="")
    location = Column(String, default="")
    url = Column(String, default="")
    description = Column(Text, default="")
    discovered_at = Column(DateTime, default=datetime.utcnow)


class Application(Base):
    """A user's candidacy for a specific job — this is per-tenant."""
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)

    matched_profile = Column(String, default="")
    match_score = Column(Integer, default=0)
    match_reason = Column(Text, default="")

    status = Column(String, default="pending_approval", server_default="pending_approval")
    # pending_approval | approved | rejected | submitted | interviewing |
    # offer | declined | closed

    tailored_resume_path = Column(String, default="", server_default="")
    notes = Column(Text, default="", server_default="")

    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())
    submitted_at = Column(DateTime, nullable=True)

    owner = relationship("User", back_populates="applications")
    job = relationship("Job")


class UsageLog(Base):
    """Tracks API-cost actions per user per calendar month, so free-tier
    limits can be enforced before an expensive Claude call is made."""
    __tablename__ = "usage_logs"
    __table_args__ = (UniqueConstraint("user_id", "period", "action", name="uq_user_period_action"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    period = Column(String, nullable=False)   # "YYYY-MM"
    action = Column(String, nullable=False)   # "match" | "tailor_resume"
    count = Column(Integer, default=0)
