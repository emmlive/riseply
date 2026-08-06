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
    token_version = Column(Integer, default=0, server_default="0")  # bumped on password reset to invalidate old JWTs
    is_admin = Column(Boolean, default=False, server_default="false")
    full_name = Column(String, default="")
    phone = Column(String, default="")
    location = Column(String, default="")
    linkedin_url = Column(String, default="")
    portfolio_url = Column(String, default="")

    resume_text = Column(Text, default="")

    notify_email = Column(String, default="")  # defaults to account email if blank
    auto_submit = Column(Boolean, default=False)  # per-user override, defaults OFF

    tos_accepted_at = Column(DateTime, nullable=True)

    # Billing
    subscription_tier = Column(String, default="free", server_default="free")  # free | pro
    subscription_status = Column(String, default="", server_default="")  # active | past_due | canceled | ""
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)

    # Rise Index — effort-based gamification, never tied to outcomes
    rise_points = Column(Integer, default=0, server_default="0")
    current_streak = Column(Integer, default=0, server_default="0")
    longest_streak = Column(Integer, default=0, server_default="0")
    last_active_date = Column(Date, nullable=True)

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
    min_match_score = Column(Integer, default=60)
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
    tenure_hint = Column(String, default="", server_default="")
    # "" (came through normal matching) | "just_started" | "a_few_months" |
    # "well_established" -- set when a user adds a job they already have,
    # via the manual entry point rather than Riseply's own matching. Lets
    # Job Buddy generate a genuinely different kind of plan (onboarding vs.
    # ongoing growth/support) instead of giving a "your first 90 days"
    # plan to someone who's been in the role for two years.

    status = Column(String, default="pending_approval", server_default="pending_approval")
    # pending_approval | approved | rejected | submitted | interviewing |
    # offer | declined | closed

    tailored_resume_path = Column(String, default="", server_default="")
    notes = Column(Text, default="", server_default="")

    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())
    status_updated_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())
    submitted_at = Column(DateTime, nullable=True)

    owner = relationship("User", back_populates="applications")
    job = relationship("Job")


class InterviewPrep(Base):
    """Generated once per application when it moves to 'interviewing' —
    likely questions, talking points, and questions to ask them."""
    __tablename__ = "interview_preps"

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    brief = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())

    application = relationship("Application")


class OnboardingPlan(Base):
    """Generated once per application when it moves to 'accepted' — a
    30/60/90-day plan, first-week checklist, and questions to ask a manager.
    This is the basis the Job Buddy chat draws context from."""
    __tablename__ = "onboarding_plans"

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    plan = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())

    application = relationship("Application")


class JobBuddyMessage(Base):
    """One turn in the ongoing onboarding-mentor chat, scoped to a specific
    accepted application (a user might have multiple over time — each gets
    its own conversation thread)."""
    __tablename__ = "job_buddy_messages"

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class PointsEvent(Base):
    """One Rise Points award. Kept as a log (not just a running total) so
    the activity feed can show a real history — 'why do I have 340 points'
    should always have a visible answer."""
    __tablename__ = "points_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    amount = Column(Integer, nullable=False)
    reason = Column(String, nullable=False)  # short human-readable label
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class PasswordResetToken(Base):
    """A single-use, short-lived password reset token. We store a hash of
    the token, never the raw value -- same principle as password hashing,
    so a database leak alone can't be used to reset anyone's password."""
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    token_hash = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


class SupportMessage(Base):
    """Persisted so admins can view and reply in-app, not just receive a
    one-off email that's easy to lose track of."""
    __tablename__ = "support_messages"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    subject = Column(String, default="")
    message = Column(Text, default="")
    status = Column(String, default="open", server_default="open")  # open | resolved

    admin_reply = Column(Text, nullable=True)
    replied_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class FailureLog(Base):
    """Logged whenever a metered Claude API call fails (i.e. whenever
    usage.decrement() is called to refund a failed attempt). This is a
    real signal, not a synthetic one -- it only fires at the exact points
    where a paid call genuinely failed."""
    __tablename__ = "failure_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


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
