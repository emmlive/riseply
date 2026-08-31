from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date, Boolean, ForeignKey,
    UniqueConstraint, func, LargeBinary,
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

    # Durable (not single-use, not short-lived like PasswordResetToken)
    # token authorizing GET /bookmarklet.js -- that endpoint has to be
    # publicly fetchable via a plain <script src="..."> tag (which can't
    # attach an Authorization header the way a normal API call can), so
    # this token in the URL itself is the only practical way to identify
    # whose data to serve. Generated lazily on first request rather than
    # at signup, same pattern already used elsewhere in this codebase.
    # Regenerable (see POST /me/regenerate-bookmarklet-token) to
    # invalidate a previously-issued bookmarklet link if it's ever
    # exposed somewhere it shouldn't be -- not a security downgrade from
    # the old fully-inline bookmarklet design (which baked the exact
    # same profile fields into a plaintext, permanently-unrevocable
    # URL); if anything this is strictly more revocable than what it
    # replaces.
    bookmarklet_token = Column(String, nullable=True, unique=True, index=True)

    # True after this user's very first "Find new matches" click has
    # run -- see routers/pipeline.py's use of this to grant a one-time,
    # unmetered "welcome search" that scores far more jobs than a
    # normal click (settings.welcome_search_job_cap, well above either
    # tier's regular per-click depth) without touching the monthly
    # match quota. The goal is a genuinely strong first impression --
    # someone's very first search should feel comprehensive, not
    # limited by the same tight per-click cap every subsequent search
    # gets, and for a free-tier user this is also a real, felt preview
    # of what Pro's deeper searches are like every time.
    used_welcome_search = Column(Boolean, default=False, server_default="false")

    resume_text = Column(Text, default="")

    notify_email = Column(String, default="")  # defaults to account email if blank
    # "off" | "every_match" | "daily_digest" -- controls the new-match
    # email notifier.notify_new_match() sends. Applies regardless of
    # what triggered the match (manual "Find new matches" click or the
    # scheduled daily run) -- same preference, same behavior either way,
    # rather than a confusing split where manual clicks always notify
    # but the scheduled run respects the setting.
    notification_preference = Column(String, default="every_match", server_default="every_match")
    # "email" | "sms" | "both" -- which channel(s) notification_preference
    # actually gets delivered through. Kept as a separate field rather
    # than folding into notification_preference's off/every_match/
    # daily_digest values, since frequency and channel are independent
    # choices -- combining them would mean 6+ enum values instead of 2
    # orthogonal ones.
    notification_channel = Column(String, default="email", server_default="email")
    # Explicit TCPA opt-in -- required before notification_channel can
    # include "sms" at all (enforced in routers/me.py, not just assumed
    # true because a phone number happens to be on file). Separate from
    # every other "I agree to..." checkbox in this app since SMS
    # consent specifically has to be its own affirmative action, not
    # bundled into ToS/Privacy/Subscription agreement.
    sms_consent = Column(Boolean, default=False, server_default="false")
    sms_consent_at = Column(DateTime, nullable=True)
    # Only matches scoring at or above this get emailed at all, on top
    # of whatever notification_preference says. 0 = no floor.
    notification_min_score = Column(Integer, default=0, server_default="0")
    # Last time this user's daily digest was actually sent -- lets the
    # digest job query "what's new since last time" per user instead of
    # a fixed 24h window, so it stays correct regardless of when in the
    # day matches actually landed (manual clicks happen at arbitrary
    # times, not just during the scheduled run).
    last_digest_sent_at = Column(DateTime, nullable=True)
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


class Resume(Base):
    """Multiple resumes per user, one marked default. User.resume_text
    is deliberately KEPT as-is and always kept in sync with whichever
    Resume row is_default -- every existing consumer across the app
    (matching, tailoring, interview prep, the extension's scoring and
    autofill) reads user.resume_text directly and continues to work
    completely unchanged. All the actual multi-resume logic (set
    default, add, rename, delete) lives in routers/resumes.py and is
    the ONLY code responsible for keeping that mirror in sync -- see
    _sync_default_to_user() there rather than duplicating this logic
    anywhere else."""
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    label = Column(String, default="")
    resume_text = Column(Text, default="")
    is_default = Column(Boolean, default=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())

    owner = relationship("User", backref="resumes")


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

    # --- Salary (currently only populated by the Adzuna source --
    # Greenhouse/Lever/RSS postings essentially never state a salary in
    # a structured field, so these stay NULL/False for those rows;
    # nullable rather than defaulting to 0 so the frontend can tell
    # "no data" apart from "an actual $0 salary"). is_predicted
    # distinguishes a real advertised figure from Adzuna's own salary
    # model -- shown to the person so a predicted range isn't mistaken
    # for what the employer actually stated.
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    salary_currency = Column(String, default="")
    salary_is_predicted = Column(Boolean, default=False)


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

    # Display filename only now, e.g. "Acme_Corp.docx" -- NOT a real
    # filesystem path. Render's web service disk is ephemeral: any file
    # written to local disk vanishes on the next deploy/restart, while
    # this row survives (Postgres is the persistent store). The actual
    # document lives in tailored_resume_data below; this column is kept
    # only so the download link can show a sensible filename.
    tailored_resume_path = Column(String, default="", server_default="")
    tailored_resume_data = Column(LargeBinary, nullable=True)
    # Short, honest explanation of what changed in the tailored resume
    # and why -- generated in the same Claude call as the tailoring
    # itself, so this costs nothing extra. See resume_customizer.py's
    # tailor_resume_text() for how it's produced. Empty string if the
    # model's response didn't follow the expected format -- the
    # tailoring itself still succeeds either way, this is additive.
    tailoring_rationale = Column(Text, default="", server_default="")
    notes = Column(Text, default="", server_default="")

    # --- Archivable pattern ---
    # Standard convention for "let a user hide something from their
    # default view without deleting it": is_archived + archived_at,
    # exactly these two column names/types. Application is the first
    # model to use it, but the pattern (not just these two columns) is
    # meant to be copied verbatim onto any future list that grows
    # unbounded and needs the same "clean up my view, don't lose my
    # data" behavior -- see the archive/unarchive endpoints in
    # routers/pipeline.py for the matching request-handling half of
    # this convention.
    is_archived = Column(Boolean, default=False, server_default="false")
    archived_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())
    status_updated_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())
    submitted_at = Column(DateTime, nullable=True)

    owner = relationship("User", back_populates="applications")
    job = relationship("Job")
    organization = relationship("Organization")


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


class CannedReply(Base):
    """A reusable reply template a support admin can insert into the
    reply textarea with one click, then edit before sending -- never
    sent automatically/unedited. Meant to help one person cover more
    ground on repetitive questions without literally being a bigger
    team."""
    __tablename__ = "canned_replies"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class EnterpriseBillingRequest(Base):
    """An org admin's request to move off self-serve card billing onto
    invoiced (NET-30 style) terms -- deliberately NOT an automated
    invoicing system. Real payment/billing integrations built under
    time pressure carry real financial risk if subtly wrong; capturing
    the request and routing it to a human to set up properly (a real
    Stripe Invoice, or whatever the actual arrangement ends up being)
    is the honest, safe version of this feature."""
    __tablename__ = "enterprise_billing_requests"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    requested_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    billing_contact_name = Column(String, nullable=False)
    billing_contact_email = Column(String, nullable=False)
    estimated_employees = Column(Integer, default=0, server_default="0")
    notes = Column(Text, default="")
    status = Column(String, default="pending", server_default="pending")  # pending | contacted | resolved
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class OrgSSOConfig(Base):
    """Enterprise SSO for one org, via a standard OIDC (OpenID Connect)
    identity provider -- Okta, Azure AD, Google Workspace, or any other
    OIDC-compliant IdP the org's IT team already uses.

    Deliberately OIDC, not raw SAML: an OIDC ID token is a signed JWT
    that can be verified with a well-established library (this app
    already depends on python-jose for its own auth tokens) against
    the provider's published public keys. Hand-rolling SAML's XML
    signature verification is a notorious source of real
    vulnerabilities even in mature libraries -- not a risk worth taking
    under time pressure for a feature this security-critical, and OIDC
    covers the same practical need for every IdP that matters here.

    allowed_email_domain is a real safety boundary, not just metadata:
    unlike Google/Microsoft (universally-trusted top-level identity
    providers this app already integrates with directly), this is an
    org-configured, narrower-scope integration -- restricting it to a
    specific email domain limits the blast radius if the integration
    is ever misconfigured."""
    __tablename__ = "org_sso_configs"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_org_sso_config"),)

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    provider_name = Column(String, default="")  # display only, e.g. "Okta"
    issuer = Column(String, nullable=False)  # e.g. https://acme.okta.com
    client_id = Column(String, nullable=False)
    client_secret = Column(String, nullable=False)
    allowed_email_domain = Column(String, nullable=False)
    enabled = Column(Boolean, default=True, server_default="true")
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class SSOLoginState(Base):
    """A short-lived, single-use CSRF token for the SSO login flow.
    Database-backed rather than a cookie specifically because the
    frontend (riseply.com) and backend (a separate Render subdomain)
    are different origins -- a cookie set during the redirect-to-IdP
    step wouldn't reliably come back on the frontend's later POST to
    the callback endpoint. Checked for expiry and deleted on first use
    (see routers/sso.py) so it can't be replayed."""
    __tablename__ = "sso_login_states"

    id = Column(Integer, primary_key=True)
    state = Column(String, unique=True, nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
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
    # Optional logo shown on the org's own dashboard and to its employees
    # on Job Buddy / onboarding pages -- a URL to an already-hosted image
    # rather than a real upload, since there's no image storage (S3,
    # Cloudflare R2, etc.) wired up anywhere in this codebase yet.
    logo_url = Column(String, default="", server_default="")
    # True only for an admin's personal pilot/practice org, created via
    # POST /orgs/sandbox -- never set by the normal self-serve org
    # creation flow. Lets an admin genuinely exercise every Org Buddy
    # feature (checklist, content, lessons, Ghost Onboarder) under their
    # own account without ever touching a real customer's data, and
    # without polluting real revenue/seat metrics -- every place that
    # aggregates across organizations excludes rows where this is true.
    is_sandbox = Column(Boolean, default=False, server_default="false")

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
    # Free-text-ish but constrained to a known set at the API layer
    # (see CONTENT_CATEGORIES in routers/org_buddy.py) -- lets an admin
    # label what a piece of content is FOR (e.g. "Mentoring Resource",
    # "Wellbeing") without needing a separate table. Purely
    # organizational/display -- doesn't change how content is folded
    # into the onboarding assistant's context, which still uses
    # everything regardless of category.
    category = Column(String, default="General", server_default="General")
    # Optional link to an already-hosted image/video/document -- see
    # security note on this field's twin in OrgLesson below; validated
    # identically (http/https only, enforced server-side in
    # routers/org_buddy.py, never trust client-side validation alone).
    media_url = Column(String, default="", server_default="")
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
    # Distinguishes the general contact pool (anyone can request a
    # handoff to any of them) from the mentor pool specifically, which
    # gets explicitly 1:1 assigned to individual employees via
    # MentorAssignment below, rather than just being suggested broadly.
    is_mentor = Column(Boolean, default=False, server_default="false")
    # Free-text expertise/background, e.g. "10 years in backend infra,
    # previously mentored 3 new grads" -- only meaningful when
    # is_mentor=True. This is the signal mentor_matcher.py scores
    # against; without it there's nothing for AI-assisted matching to
    # compare an employee's resume/goals to beyond a bare job title.
    # Kept as free text rather than structured skill tags since a
    # mentor writing "I'm good at helping people navigate ambiguity"
    # is more useful signal than picking from a fixed tag list, and is
    # less setup effort per mentor for the admin who enters it.
    mentor_bio = Column(Text, default="", server_default="")
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class MentorAssignment(Base):
    """Pairs one employee (via their org-linked Application) with one
    mentor (an OrgHumanContact row with is_mentor=True). Deliberately
    reuses OrgHumanContact/HandoffRequest wholesale rather than
    building parallel infrastructure -- a mentor IS a human contact,
    just one that's been explicitly 1:1 assigned instead of left in
    the general pool anyone can reach out to. 'Request an intro' from
    an assigned mentor uses the exact same HandoffRequest flow already
    built for the general contact list (a note the employee wrote,
    never their chat history).

    One row per application (see the unique constraint) -- reassigning
    to a different mentor UPDATES this same row's contact_id rather
    than creating a new one (see assign_mentor in routers/org_buddy.py).
    That means ended_at/end_reason reflect the CURRENT pairing's
    status, not a full history of every past mentor this employee has
    had; assign_mentor resets ended_at to None on reassignment so a
    fresh pairing always starts active. A MentorRetrospective from a
    prior, since-reassigned pairing stays in the database (linked by
    mentor_assignment_id) but is no longer meaningfully "about" the
    current contact_id -- acceptable today only because the analytics
    this feeds are org-wide aggregates, not a per-mentor performance
    breakdown; that would need this table restructured to preserve
    full history first."""
    __tablename__ = "mentor_assignments"
    __table_args__ = (UniqueConstraint("application_id", name="uq_application_mentor"),)

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    contact_id = Column(Integer, ForeignKey("org_human_contacts.id"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())
    # reminder_last_sent_at tracks the mentorship check-in nudge
    # (see mentor_reminders.py), separate from any other reminder
    # system in the app -- guards against re-notifying every single
    # day once a pairing has gone quiet, the same guard pattern
    # ChecklistItem/LessonDelivery reminders already use elsewhere.
    reminder_last_sent_at = Column(DateTime, nullable=True)
    # Set by an admin via POST .../end -- gates whether a retrospective
    # can be submitted (see MentorRetrospective below). Deliberately
    # NOT auto-set by anything (e.g. inactivity) -- ending a real
    # relationship should be a deliberate action, not an inferred one.
    ended_at = Column(DateTime, nullable=True)
    end_reason = Column(String, default="", server_default="")


class MentorRetrospective(Base):
    """One employee's end-of-pairing reflection: what worked, what
    didn't, and whether they'd recommend this mentor to others. Only
    submittable once the pairing has been marked ended (see
    ended_at above) -- a retrospective is inherently about a
    CONCLUDED relationship, not an ongoing one.

    Employee-submitted only (not the mentor) -- same reasoning as
    MentorMeetingLog.feedback_note being employee-owned: this is the
    employee's own honest assessment, and we want candor over the
    mentor being able to see or react to it.

    what_worked/what_didnt_work are intentionally private -- visible
    only to the employee who wrote them, never to the admin or the
    mentor -- same privacy boundary as meeting feedback_note. Only
    would_recommend_mentor (a plain boolean) rolls up into aggregate
    analytics, the same "counts and rates, never the actual words"
    principle used everywhere else in Org Buddy's reporting."""
    __tablename__ = "mentor_retrospectives"
    __table_args__ = (UniqueConstraint("mentor_assignment_id", name="uq_mentor_assignment_retrospective"),)

    id = Column(Integer, primary_key=True)
    mentor_assignment_id = Column(Integer, ForeignKey("mentor_assignments.id"), nullable=False)
    what_worked = Column(Text, default="", server_default="")
    what_didnt_work = Column(Text, default="", server_default="")
    would_recommend_mentor = Column(Boolean, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class MentorMeetingLog(Base):
    """One logged meeting between a mentor and mentee, tied to the
    MentorAssignment (not directly to the employee or mentor) since a
    log entry only makes sense in the context of a specific pairing --
    if the mentor is ever reassigned, old logs stay attached to the
    original pairing they actually happened under, not silently
    reattributed to whoever replaces that mentor.

    rating/feedback_note are OPTIONAL and employee-submitted after the
    fact -- a mentor logging that a meeting happened doesn't require
    the employee to have rated it, and the two are recorded separately
    so a missing rating doesn't block the meeting record itself from
    counting toward participation stats.

    Aggregated into org_analytics as counts/averages only, never
    surfaced per-entry to admins -- same privacy boundary as chat
    content and CareerGoal: what was discussed is the pair's own
    business, only that meetings are happening (and roughly how
    they're rated) is fair game for program-health reporting."""
    __tablename__ = "mentor_meeting_logs"

    id = Column(Integer, primary_key=True)
    mentor_assignment_id = Column(Integer, ForeignKey("mentor_assignments.id"), nullable=False)
    logged_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    meeting_date = Column(Date, nullable=False)
    notes = Column(Text, default="", server_default="")
    rating = Column(Integer, nullable=True)  # 1-5, optional, employee-submitted
    feedback_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class CareerGoal(Base):
    """A short-term growth goal the employee set for themselves via Job
    Buddy -- persisted so ongoing guidance can be grounded in what THIS
    specific person said they want to work on, instead of starting
    fresh every conversation. This is the AI-mentorship half of the
    feature; MentorAssignment above is the human-pairing half.

    Employee-owned and employee-visible only. Deliberately NOT surfaced
    in org admin analytics -- unlike checklist/lesson data (enrollment
    and progress signals, fair game for aggregate reporting), a
    person's stated career goals are personal content, same privacy
    boundary as their Job Buddy chat itself."""
    __tablename__ = "career_goals"

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    goal_text = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())
    achieved_at = Column(DateTime, nullable=True)


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
    media_url = Column(String, default="", server_default="")
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


class OrgQALog(Base):
    """One instant Q&A exchange between an employee and the org's
    content-scoped assistant ('Ghost Onboarder'). Kept as a log, not
    ephemeral, so an org admin can see what new hires are actually
    asking -- the same signal a human HR team builds from watching
    their inbox, and a direct pointer to gaps worth filling in their
    uploaded content. Answer text only, never the employee's private
    Job Buddy conversation -- this is a separate, narrower feature."""
    __tablename__ = "org_qa_logs"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    question = Column(Text, default="")
    answer = Column(Text, default="")
    # False means nothing in the org's uploaded content matched -- the
    # answer told the employee that plainly rather than guessing. A
    # cluster of these is a strong signal for what to add to the KB.
    matched_content = Column(Boolean, default=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class OrgLesson(Base):
    """An admin-authored micro-lesson template for the spaced-repetition
    'Culture Bot' -- delivered day_offset days after an employee's
    application record was created (their join date, for org-linked
    applications). department_id NULL means company-wide, same layering
    as checklist items and content. quiz_question/quiz_answer are
    optional and deliberately simple: a short free-text prompt graded
    by case-insensitive substring match, not an LLM -- no ambiguity
    about why an answer was marked right or wrong."""
    __tablename__ = "org_lessons"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    day_offset = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    quiz_question = Column(String, default="", server_default="")
    quiz_answer = Column(String, default="", server_default="")
    # Optional link to an already-hosted image/video/document (a
    # welcome video, a handbook PDF on Drive, etc.) -- URL only, never
    # a real upload: there's no object storage set up anywhere in this
    # codebase, and storing images/video as Postgres BLOBs (the
    # pattern used for tailored resumes, which are small Word docs)
    # would be genuinely bad practice at video-file sizes. Rendering is
    # deliberately conservative: only a small allowlist of known video
    # providers (YouTube/Vimeo/Loom) get an actual iframe embed, built
    # from a backend-extracted video ID rather than trusting a raw
    # user-supplied embed URL; everything else renders as a plain,
    # noopener-safe link. The backend never fetches this URL itself
    # (no SSRF surface) -- the browser loads it directly, and only
    # http/https schemes are accepted, validated server-side.
    media_url = Column(String, default="", server_default="")
    order = Column(Integer, default=0, server_default="0")
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class LessonDelivery(Base):
    """One lesson actually sent to one employee. The unique constraint is
    what makes delivery idempotent -- the daily delivery run can be
    triggered more than once on the same day (retry, manual re-run)
    without double-sending, since it always checks for an existing row
    first."""
    __tablename__ = "lesson_deliveries"
    __table_args__ = (UniqueConstraint("application_id", "lesson_id", name="uq_app_lesson"),)

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    lesson_id = Column(Integer, ForeignKey("org_lessons.id"), nullable=False)
    delivered_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())
    quiz_response = Column(String, nullable=True)
    quiz_correct = Column(Boolean, nullable=True)
    reminder_sent_at = Column(DateTime, nullable=True)


class ScoredJob(Base):
    """Every job a user's matcher has actually evaluated, regardless of
    outcome (became an Application, was a near-miss, or just scored
    below threshold with nothing recorded). Application rows already
    exclude a job from future 'Find new matches' runs once it becomes
    a real match -- this is the missing other half: without it, a job
    that scored below threshold gets re-evaluated (and re-billed
    against the user's monthly match quota) on every single run,
    forever, since nothing ever marked it as already checked. That
    meant repeated runs mostly re-scored the same jobs near the front
    of the pool instead of making progress through the rest of it.

    Only written on a genuinely successful score (see
    pipeline_runner.run_matching_for_user) -- a job that errored out
    (e.g. a transient Claude API failure) is deliberately left
    unmarked so a later run retries it instead of silently
    blacklisting it over a one-off failure."""
    __tablename__ = "scored_jobs"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_user_job_scored"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    scored_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


class NearMissResult(Base):
    """The 'Closest this run' near-misses from the LAST run that didn't
    produce a real match -- a snapshot of 'what came closest last
    time', not a growing history. All existing rows for a user get
    replaced every time run_matching_for_user() computes a fresh
    near-miss list (see its use in pipeline_runner.py).

    Before this model existed, near-misses only ever lived in the
    frontend's React state, populated directly from the one-time
    POST /pipeline/match response -- an ordinary page refresh silently
    erased them, even though a real Application from that same run
    would have survived (because Applications DO persist to the
    database). This closes that gap the same way: mirrors
    Application's shape (job_id FK + a score/reason/matched_profile
    snapshot, with title/company/url/salary fetched via the Job
    relationship at display time) rather than duplicating those
    fields here.
    """
    __tablename__ = "near_miss_results"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)

    score = Column(Integer, default=0)
    reason = Column(Text, default="")
    matched_profile = Column(String, default="")
    # True when this result only surfaced via run_matching_for_user's
    # location-fallback pass (see matcher.best_profile_match's
    # ignore_location option) -- lets the frontend keep showing the
    # same "Outside your preferred location" label after a page
    # refresh that it showed in the original POST response.
    location_mismatch = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())

    job = relationship("Job")


class ScheduledRunLog(Base):
    """Tracks a single execution of a backend-heavy scheduled job
    (currently just /internal/scheduled-run's discovery+matching batch)
    that's kicked off via FastAPI's BackgroundTasks rather than run
    inline in the request/response cycle.

    Exists because moving that work to a background task means the
    triggering request (a single GitHub Actions curl call) can no
    longer tell success from failure just from its own HTTP response --
    it gets back a 202 the instant the task is *queued*, not when it's
    *done*. This table is what the external scheduler polls via
    GET /internal/scheduled-run/{id} to find out how it actually went,
    and what a human can check after the fact without digging through
    Render logs.

    run_type distinguishes which job this is, in case another
    long-running job (besides scheduled matching) ever needs the same
    background+poll pattern -- one table, not one per job type.
    """
    __tablename__ = "scheduled_run_logs"

    id = Column(Integer, primary_key=True)
    run_type = Column(String, nullable=False)  # "scheduled_run" (room to grow)
    status = Column(String, nullable=False, default="running", server_default="running")  # running | success | failed
    result_json = Column(Text, nullable=True)  # JSON summary, set on success
    error = Column(Text, nullable=True)  # str(exception), set on failure
    started_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())
    finished_at = Column(DateTime, nullable=True)


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
