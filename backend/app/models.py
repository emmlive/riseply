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
    admin_role = Column(String, default="", server_default="")  # "" | super | support | billing | readonly
    is_suspended = Column(Boolean, default=False, server_default="false")
    suspended_at = Column(DateTime, nullable=True)
    suspended_reason = Column(String, default="", server_default="")
    oauth_provider = Column(String, nullable=True)  # "google" | "microsoft" | None (password-based account)
    full_name = Column(String, default="")
    phone = Column(String, default="")
    location = Column(String, default="")
    linkedin_url = Column(String, default="")
    portfolio_url = Column(String, default="")

    resume_text = Column(Text, default="")

    notify_email = Column(String, default="")  # defaults to account email if blank
    auto_submit = Column(Boolean, default=False)  # per-user override, defaults OFF

    tos_accepted_at = Column(DateTime, nullable=True)
    subscription_terms_accepted_at = Column(DateTime, nullable=True)

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
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    # Set when this application was created via an org's join code --
    # its onboarding plan/chat draws on that org's uploaded custom
    # content (handbook, culture, department info) in addition to the
    # normal resume + job info.
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    # Set when joined via a department-specific code rather than the
    # org-wide code -- plan/chat then also draws on that department's
    # own content, layered on top of the company-wide material.
    manager_email = Column(String, default="", server_default="")
    # From the roster entry, if the admin provided one. Used only to
    # send a factual completion notification when the checklist hits
    # 100% -- never any conversation content.
    manager_notified_at = Column(DateTime, nullable=True)
    # Guards against re-notifying the manager every time (e.g. if an
    # admin adds a new checklist item after the employee already
    # finished, re-completing it shouldn't re-fire the notification).

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

    # --- Trust & safety flagging ---
    # Set by a lightweight keyword scan (see services/safety_flags.py) run
    # against both the user's message and the assistant's reply. This is a
    # coarse signal for a human admin to review, never an automated
    # moderation action -- nothing is blocked or altered based on it.
    flagged = Column(Boolean, default=False, server_default="false")
    flag_reason = Column(String, default="", server_default="")
    flag_resolved_at = Column(DateTime, nullable=True)


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


class Organization(Base):
    """A company using 'Org Buddy as a Service' -- their own customized
    version of the traditional workplace onboarding-buddy practice,
    grounded in real company materials rather than generic advice."""
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    join_code = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())

    # --- Billing: hybrid (base plan + per-seat overage) ---
    plan = Column(String, default="", server_default="")  # "" | starter | growth | enterprise
    subscription_status = Column(String, default="", server_default="")
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    included_seats = Column(Integer, default=0, server_default="0")


class Department(Base):
    """A department within an org (Finance, Engineering, etc.) -- has its
    own join code, distinct from the org-wide one. Someone joining with
    the org-wide code gets company-wide content only; someone joining
    with a department code gets company-wide content PLUS that
    department's own material layered on top."""
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_org_department_name"),)

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    name = Column(String, nullable=False)
    join_code = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class OrganizationMember(Base):
    """Links a User to an Organization. role is 'admin' (manages the
    whole org, every department), 'department_admin' (manages only their
    own department's content/contacts/roster -- department_id required),
    or 'employee' (just uses their join code once; department_id is set
    if they joined via a department-specific code, null if they joined
    via the org-wide code)."""
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_org_user"),)

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String, default="employee", server_default="employee")  # admin | department_admin | employee
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class OrganizationBuddyContent(Base):
    """Custom onboarding material an org admin (or department admin, for
    their own department) has uploaded -- handbook excerpts, culture
    doc, department-specific info. department_id NULL means company-wide
    (folded into every employee's plan/chat regardless of department);
    set means it only applies to that specific department's employees,
    layered on top of the company-wide material."""
    __tablename__ = "organization_buddy_content"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    title = Column(String, default="")
    content = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class OrgRosterEntry(Base):
    """A pre-registered expected employee, uploaded by an org admin via
    CSV, so a new hire doesn't have to hand-type their own title/tenure
    when they join -- the org already told us. This is enrollment/roster
    data (did this specific person join yet), NOT conversation content --
    that distinction matters: an admin seeing 'Jane hasn't joined yet' is
    normal onboarding-coordination visibility (like an LMS showing who's
    completed a training module), fundamentally different from an admin
    seeing what Jane said to her buddy, which stays private always."""
    __tablename__ = "org_roster_entries"
    __table_args__ = (UniqueConstraint("organization_id", "email", name="uq_org_roster_email"),)

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    email = Column(String, nullable=False)
    title = Column(String, default="")
    tenure = Column(String, default="just_started")
    manager_email = Column(String, default="", server_default="")
    matched_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # set once they actually join
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class OrgHumanContact(Base):
    """A real person at the company an employee can be handed off to for
    things AI structurally can't do -- an office tour, a face-to-face
    intro, physical equipment setup. Fed into the Job Buddy prompt so it
    can naturally mention the right person, and selectable when an
    employee explicitly requests a handoff. department_id NULL means
    company-wide (suggested to every employee); set means only suggested
    to that specific department's employees."""
    __tablename__ = "org_human_contacts"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    description = Column(String, default="")  # e.g. "Office tours & facilities"
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class OrgChecklistItem(Base):
    """A checklist item template an admin (or department admin, for
    their own department) has defined -- e.g. 'Set up your laptop',
    'Complete expense system training'. department_id NULL means
    company-wide (every employee gets it); set means only that
    department's employees get it, same layering as content/contacts.

    policy_content, if set, turns this into a policy-acknowledgment item
    rather than a plain task -- the employee must actually read this
    text before an explicit acknowledgment (not a bare checkbox) marks
    it complete. Used for things like a Code of Ethics or anti-
    harassment policy where the organization needs a real record of
    what was agreed to, not just that a box got checked."""
    __tablename__ = "org_checklist_items"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    title = Column(String, nullable=False)
    description = Column(String, default="")
    policy_content = Column(Text, nullable=True)
    order = Column(Integer, default=0, server_default="0")
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class ChecklistCompletion(Base):
    """Tracks one employee's completion of one checklist item.
    Enrollment/progress data, not conversation content -- same category
    as roster 'joined' status, safe for admin visibility.

    policy_content_snapshot captures the EXACT text of the policy at the
    moment of acknowledgment, independent of the live OrgChecklistItem --
    this is what makes it a real compliance record: if the org edits the
    policy later, this employee's acknowledgment still shows precisely
    what they agreed to, not whatever the policy currently says."""
    __tablename__ = "checklist_completions"
    __table_args__ = (UniqueConstraint("application_id", "checklist_item_id", name="uq_app_checklist_item"),)

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    checklist_item_id = Column(Integer, ForeignKey("org_checklist_items.id"), nullable=False)
    policy_content_snapshot = Column(Text, nullable=True)
    completed_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class HandoffRequest(Base):
    """An employee-initiated request to connect with a real human contact.
    Deliberately carries ONLY what the employee themselves wrote in
    `note` -- never their Job Buddy chat history. This is what keeps the
    handoff consistent with the privacy model: the employee controls
    exactly what leaves their private conversation, nothing is
    auto-summarized or silently forwarded on their behalf."""
    __tablename__ = "handoff_requests"

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    contact_id = Column(Integer, ForeignKey("org_human_contacts.id"), nullable=False)
    note = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class KnowledgeBaseArticle(Base):
    """Riseply-wide help content (not org-specific -- see
    OrganizationBuddyContent for that). Admin-curated, and the ONLY
    source the KB assistant is allowed to answer from -- deliberately
    never lets the model answer from general knowledge about how
    similar products typically work, since that could be confidently
    wrong about Riseply's actual pricing, privacy behavior, or feature
    details."""
    __tablename__ = "kb_articles"

    id = Column(Integer, primary_key=True)
    category = Column(String, default="General")
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now())


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
