from datetime import datetime, date
from typing import Optional
from pydantic import field_validator, model_validator, BaseModel, EmailStr, Field


# --- Auth ---

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = ""
    agree_to_terms: bool = False
    agree_to_subscription_terms: bool = False
    captcha_token: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class OAuthCallbackRequest(BaseModel):
    code: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str


class CalendarConnectionOut(BaseModel):
    provider: str
    connected_at: datetime


class CalendarConnectUrlOut(BaseModel):
    url: str
    state: str


class CalendarCallbackRequest(BaseModel):
    code: str = Field(min_length=1)
    token_type: str = "bearer"


# --- User profile ---

class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    phone: str
    location: str
    linkedin_url: str
    portfolio_url: str
    notify_email: str
    auto_submit: bool
    notification_preference: str = "every_match"
    notification_min_score: int = 0
    notification_channel: str = "email"
    sms_consent: bool = False
    resume_text: str
    subscription_tier: str
    subscription_status: str
    is_admin: bool
    admin_role: str
    bookmarklet_token: str = ""
    used_welcome_search: bool = False
    # Complimentary Pro access from a free-days discount code, if any.
    pro_until: datetime | None = None

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    notify_email: Optional[str] = None
    auto_submit: Optional[bool] = None
    notification_preference: Optional[str] = None
    notification_min_score: Optional[int] = Field(default=None, ge=0, le=100)
    notification_channel: Optional[str] = None
    sms_consent: Optional[bool] = None


class ResumeUpdate(BaseModel):
    resume_text: str


class ResumeParseOut(BaseModel):
    resume_text: str


# --- Search profiles ---

class SearchProfileIn(BaseModel):
    name: str
    titles: list[str] = []
    locations: list[str] = []
    seniority: list[str] = []
    min_match_score: int = 60
    exclude_companies: list[str] = []
    keywords_required: list[str] = []
    keywords_excluded: list[str] = []
    active: bool = True


class SearchProfileOut(SearchProfileIn):
    id: int

    class Config:
        from_attributes = True


# --- Near-misses ---
# See models.NearMissResult -- these are jobs that didn't clear a
# profile's match threshold, persisted so they survive a page refresh
# (they previously only lived in frontend React state). Deliberately
# NOT built from_attributes off the ORM row directly the way
# ApplicationOut is -- title/company/url/salary live on the related
# Job row, not on NearMissResult itself, so the router assembles this
# from both (see GET /pipeline/near-misses).
class NearMissOut(BaseModel):
    title: str
    company: str
    url: str
    score: int
    reason: str
    matched_profile: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = ""
    salary_is_predicted: bool = False
    location_mismatch: bool = False
    # When the search that surfaced this ran (UTC).
    found_at: Optional[datetime] = None




class ApplicationOut(BaseModel):
    id: int
    status: str
    matched_profile: str
    match_score: int
    match_reason: str
    tailored_resume_path: str
    notes: str
    created_at: datetime
    submitted_at: Optional[datetime] = None

    job_title: str
    job_company: str
    job_location: str
    job_url: str
    organization_id: Optional[int] = None
    organization_logo_url: str = ""
    organization_accent_color: str = ""
    tailoring_rationale: str = ""
    has_tailored_resume_data: bool = False
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = ""
    salary_is_predicted: bool = False
    # False once the posting is known to be closed. The page greys the
    # job out and hides Approve.
    job_open: bool = True
    is_archived: bool = False
    archived_at: Optional[datetime] = None


class KeywordGapsOut(BaseModel):
    present: list[str]
    missing: list[str]


class FollowupOut(BaseModel):
    message: str

    class Config:
        from_attributes = True


class UsageOut(BaseModel):
    tier: str
    matches_used: int
    matches_limit: int
    tailored_resumes_used: int
    tailored_resumes_limit: int
    interview_preps_used: int
    interview_preps_limit: int
    onboarding_plans_used: int
    onboarding_plans_limit: int
    job_buddy_messages_used: int
    job_buddy_messages_limit: int


# --- Interview prep ---

class InterviewPrepOut(BaseModel):
    id: int
    application_id: int
    brief: str
    created_at: datetime

    class Config:
        from_attributes = True


# --- Job Buddy ---

class OnboardingPlanOut(BaseModel):
    id: int
    application_id: int
    plan: str
    created_at: datetime

    class Config:
        from_attributes = True


class JobBuddyMessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class JobBuddyChatRequest(BaseModel):
    message: str = Field(min_length=1)


# --- Coaching (practical, role-specific training) ---

class CoachingSessionOut(BaseModel):
    id: int
    application_id: int
    session_type: str
    topic: str
    status: str
    score: int | None
    feedback: str
    created_at: datetime
    completed_at: datetime | None

    class Config:
        from_attributes = True


class CoachingMessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class CoachingSessionStartRequest(BaseModel):
    session_type: str = Field(pattern="^(drill|walkthrough|roleplay)$")
    topic: str = Field(default="", max_length=200)
    # Left blank, the model picks a realistic topic for this role itself
    # -- see services/coaching.py's start_coaching_session().


class CoachingSessionStartResponse(BaseModel):
    session: CoachingSessionOut
    opening_message: CoachingMessageOut


class CoachingMessageRequest(BaseModel):
    message: str = Field(min_length=1)


# --- Career Coach (individual product) ---

class CareerCoachSessionOut(BaseModel):
    id: int
    session_type: str
    target_role: str
    topic: str
    status: str
    score: int | None
    feedback: str
    created_at: datetime
    completed_at: datetime | None
    learning_style: str = "auto"

    class Config:
        from_attributes = True


LEARNING_STYLES = "auto|visual|handson|story|stepbystep"


class CareerCoachStartRequest(BaseModel):
    session_type: str = Field(pattern="^(drill|walkthrough|interview|resume)$")
    target_role: str = Field(min_length=2, max_length=120)
    topic: str = Field(default="", max_length=200)
    learning_style: str = Field(default="auto", pattern=f"^({LEARNING_STYLES})$")
    # True when "read the coach's replies aloud" is on: the coach writes for
    # the ear (no markdown or symbols a speech voice would read out).
    voice: bool = False


class CareerCoachMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    voice: bool = False
    # One-off teaching style for just this reply ("explain it differently");
    # does not change the session's own learning_style.
    style: str | None = Field(default=None, pattern="^(visual|handson|story|stepbystep)$")


class VisualStep(BaseModel):
    label: str = Field(max_length=80)
    detail: str = Field(default="", max_length=240)


class VisualRow(BaseModel):
    label: str = Field(max_length=80)
    cells: list[str] = Field(default_factory=list, max_length=4)


class VisualBranch(BaseModel):
    label: str = Field(max_length=80)
    items: list[str] = Field(default_factory=list, max_length=5)


class VisualOut(BaseModel):
    """A diagram the coach drew to teach with. The model supplies only
    structured data (never HTML/SVG); the frontend draws it. kind:
      flow    -- ordered steps (a process, a timeline)
      compare -- a table: columns across, labelled rows down
      map     -- a center idea with labelled branches of short items
    """
    kind: str = Field(pattern="^(flow|compare|map)$")
    title: str = Field(default="", max_length=120)
    steps: list[VisualStep] = Field(default_factory=list, max_length=8)
    columns: list[str] = Field(default_factory=list, max_length=4)
    rows: list[VisualRow] = Field(default_factory=list, max_length=8)
    center: str = Field(default="", max_length=80)
    branches: list[VisualBranch] = Field(default_factory=list, max_length=6)


RESOURCE_TYPES = "course|article|video|book|practice|reference|tool"


class LibraryItemIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    # http(s) only -- the frontend renders this as a link, and a
    # javascript: or data: URL must never be storable.
    url: str = Field(pattern=r"^https?://\S+$", max_length=500)
    description: str = Field(default="", max_length=1000)
    resource_type: str = Field(default="course", pattern=f"^({RESOURCE_TYPES})$")
    fields: list[str] = Field(default_factory=list, max_length=8)
    level: str = Field(default="all", pattern="^(beginner|intermediate|advanced|all)$")
    cost: str = Field(default="free", pattern="^(free|freemium|paid)$")
    active: bool = True

    @field_validator("fields")
    @classmethod
    def _clean_fields(cls, v):
        out = []
        for f in v:
            f = f.strip().lower().replace(",", " ")
            if f and len(f) <= 40 and f not in out:
                out.append(f)
        return out


class LibraryItemOut(BaseModel):
    id: int
    title: str
    url: str
    description: str = ""
    resource_type: str
    fields: list[str] = []
    level: str
    cost: str
    active: bool = True

    @field_validator("fields", mode="before")
    @classmethod
    def _split_fields(cls, v):
        if isinstance(v, str):
            return [f for f in v.split(",") if f]
        return v or []

    class Config:
        from_attributes = True


class CareerCoachMessageOut(BaseModel):
    """A coach transcript message plus any Library resources the coach
    recommended in it (resolved from [[lib:ID]] markers; content is
    returned with those markers already removed)."""
    id: int
    role: str
    content: str
    created_at: datetime
    resources: list[LibraryItemOut] = []
    visual: VisualOut | None = None


class CareerCoachStartResponse(BaseModel):
    session: CareerCoachSessionOut
    opening_message: CareerCoachMessageOut


class CareerCoachNoteIn(BaseModel):
    content: str = Field(max_length=20000)


class CareerCoachNoteOut(BaseModel):
    content: str = ""
    updated_at: datetime | None = None


class StudyFolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class StudyFolderOut(BaseModel):
    id: int
    name: str
    note_count: int = 0
    created_at: datetime | None = None


class StudyNoteIn(BaseModel):
    title: str = Field(default="", max_length=160)
    content: str = Field(min_length=1, max_length=20000)
    folder_id: int | None = None
    session_id: int | None = None
    source: str = Field(default="manual", pattern="^(notepad|coach_reply|feedback|manual)$")
    source_label: str = Field(default="", max_length=160)


class StudyNoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    content: str | None = Field(default=None, min_length=1, max_length=20000)
    # Present-and-null moves the note to "Unfiled", so "not sent" and
    # "null" have to be told apart (see routers/study.py).
    folder_id: int | None = None


class StudyNoteOut(BaseModel):
    id: int
    folder_id: int | None = None
    session_id: int | None = None
    title: str = ""
    content: str = ""
    source: str = "manual"
    source_label: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AddCurrentJobRequest(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    tenure: str = Field(pattern="^(just_started|a_few_months|well_established)$")
    description: str = Field(default="", max_length=5000)
    org_join_code: str = Field(default="", max_length=40)


# --- Org Buddy as a Service ---

class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrganizationOut(BaseModel):
    id: int
    name: str
    join_code: str
    created_at: datetime
    is_sandbox: bool = False
    logo_url: str = ""
    accent_color: str = ""
    require_manager_approval_for_internal_jobs: bool = False


class OrgSettingsUpdate(BaseModel):
    logo_url: str = Field(default="", max_length=1000)
    # Same always-set-from-payload behavior as logo_url (not the
    # None-means-leave-alone treatment require_manager_approval_for_
    # internal_jobs needs) -- an empty string is a legitimate, safe
    # "no custom color" state to reset TO, same category of field as
    # the logo, not a stateful toggle with a meaningful prior value to
    # protect.
    accent_color: str = Field(default="", max_length=20)
    # None (not False) as the "don't touch this" default -- distinct
    # from an explicit False, so a settings save that doesn't know
    # about this field (e.g. a logo-only update from an older client)
    # can't silently reset it back off if it was previously turned on.
    require_manager_approval_for_internal_jobs: bool | None = None


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class DepartmentOut(BaseModel):
    id: int
    name: str
    join_code: str
    created_at: datetime


class OrgContentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20000)
    department_id: int | None = None
    media_url: str = Field(default="", max_length=2000)
    category: str = Field(default="General", max_length=50)


class OrgContentOut(BaseModel):
    id: int
    title: str
    content: str
    department_id: int | None
    media_url: str = ""
    category: str = "General"
    created_at: datetime


class OrgUsageStats(BaseModel):
    employees_joined: int
    plans_generated: int
    total_messages: int
    avg_messages_per_employee: float


class OrgRosterUploadResult(BaseModel):
    added: int
    updated: int
    errors: list[str]


class OrgRosterEntryOut(BaseModel):
    id: int
    email: str
    title: str
    tenure: str
    department_id: int | None
    manager_email: str
    joined: bool
    created_at: datetime


class OrgBillingOut(BaseModel):
    plan: str
    subscription_status: str
    included_seats: int
    employees_joined: int
    overage_seats: int
    overage_cost_usd: float


class EnterpriseBillingRequestCreate(BaseModel):
    billing_contact_name: str = Field(min_length=1, max_length=200)
    billing_contact_email: EmailStr
    estimated_employees: int = Field(default=0, ge=0, le=100000)
    notes: str = Field(default="", max_length=2000)


class EnterpriseBillingRequestOut(BaseModel):
    id: int
    organization_id: int
    billing_contact_name: str
    billing_contact_email: str
    estimated_employees: int
    notes: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class EnterpriseBillingRequestStatusUpdate(BaseModel):
    status: str


class OrgSSOConfigCreate(BaseModel):
    provider_name: str = Field(default="", max_length=100)
    issuer: str = Field(min_length=1, max_length=500)
    client_id: str = Field(min_length=1, max_length=500)
    client_secret: str = Field(min_length=1, max_length=500)
    allowed_email_domain: str = Field(min_length=1, max_length=200)


class OrgSSOConfigOut(BaseModel):
    id: int
    provider_name: str
    issuer: str
    client_id: str
    allowed_email_domain: str
    enabled: bool
    created_at: datetime
    # Deliberately no client_secret field -- write-only, same principle
    # as never returning a password hash. Once set, it can be replaced
    # but never read back through the API.

    class Config:
        from_attributes = True


class SSOCallbackRequest(BaseModel):
    code: str = Field(min_length=1, max_length=2000)
    state: str = Field(min_length=1, max_length=200)


class ChecklistItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=1000)
    policy_content: str | None = Field(default=None, max_length=20000)
    department_id: int | None = None
    order: int = 0
    media_url: str = Field(default="", max_length=2000)


class ChecklistItemOut(BaseModel):
    id: int
    title: str
    description: str
    policy_content: str | None
    department_id: int | None
    order: int
    media_url: str = ""
    created_at: datetime


class ChecklistProgressItem(BaseModel):
    id: int
    title: str
    description: str
    policy_content: str | None
    media_url: str = ""
    completed: bool
    completed_at: datetime | None


class PolicyAcknowledgment(BaseModel):
    application_id: int
    employee_email: str
    employee_name: str
    completed_at: datetime


class OrgContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    description: str = Field(default="", max_length=300)
    department_id: int | None = None
    is_mentor: bool = False
    mentor_bio: str = Field(default="", max_length=3000)


class OrgContactOut(BaseModel):
    id: int
    name: str
    email: str
    description: str
    department_id: int | None
    is_mentor: bool
    mentor_bio: str
    created_at: datetime


class HandoffRequestCreate(BaseModel):
    contact_id: int
    note: str = Field(min_length=1, max_length=2000)


class MentorAssignRequest(BaseModel):
    contact_id: int


class MentorAssignmentOut(BaseModel):
    id: int
    contact_id: int
    name: str
    email: str
    description: str
    assigned_at: datetime
    ended_at: datetime | None
    end_reason: str


class MentorAssignmentEndRequest(BaseModel):
    reason: str = Field(default="", max_length=200)


class MentorRetrospectiveCreate(BaseModel):
    what_worked: str = Field(default="", max_length=3000)
    what_didnt_work: str = Field(default="", max_length=3000)
    would_recommend_mentor: bool | None = None


class MentorRetrospectiveOut(BaseModel):
    id: int
    mentor_assignment_id: int
    what_worked: str
    what_didnt_work: str
    would_recommend_mentor: bool | None
    created_at: datetime


VALID_RELATIONSHIP_TYPES = ("group", "reciprocal")
VALID_PARTICIPANT_ROLES = ("mentor", "mentee", "peer")


class MentorshipParticipantCreate(BaseModel):
    application_id: int
    role: str = Field(min_length=1, max_length=20)


class MentorshipParticipantOut(BaseModel):
    id: int
    application_id: int
    user_full_name: str
    role: str
    added_at: datetime


class MentorshipRelationshipCreate(BaseModel):
    relationship_type: str = Field(min_length=1, max_length=20)
    name: str = Field(default="", max_length=200)
    participants: list[MentorshipParticipantCreate] = Field(min_length=2, max_length=50)


class MentorshipRelationshipOut(BaseModel):
    id: int
    relationship_type: str
    name: str
    participants: list[MentorshipParticipantOut]
    created_at: datetime
    ended_at: datetime | None
    end_reason: str


class MentorshipRelationshipEndRequest(BaseModel):
    reason: str = Field(default="", max_length=200)


class MentorshipMeetingLogCreate(BaseModel):
    meeting_date: date
    notes: str = Field(default="", max_length=2000)


class MentorshipMeetingLogOut(BaseModel):
    id: int
    relationship_id: int
    meeting_date: date
    notes: str
    created_at: datetime


class InternalJobPostingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    department_id: int | None = None
    description: str = Field(default="", max_length=3000)


class InternalJobPostingOut(BaseModel):
    id: int
    title: str
    department_id: int | None
    department_name: str | None
    description: str
    created_at: datetime
    closed_at: datetime | None
    applicant_count: int
    # Only set on the employee-facing endpoint, so an employee's own
    # browse view can show "Applied" instead of an Apply button
    # without a second round-trip -- None on the admin endpoint, which
    # has no single "current employee" to check this against.
    has_applied: bool | None = None
    # Same reasoning as has_applied -- only meaningful (and only
    # computed) on the employee-facing browse endpoint, against THAT
    # employee's own stated career goal. Never reveals the goal text
    # itself to anyone else; it's a private signal used only to
    # reorder/highlight this specific employee's own view.
    matches_your_goal: bool | None = None
    # Same has_applied/matches_your_goal pattern -- employee-facing
    # only, None on the admin endpoint. has_applied stays a plain
    # boolean for backward compatibility; this carries the actual
    # workflow state once approval routing is involved (still just
    # "approved" immediately for orgs with approval off, matching the
    # original behavior has_applied alone used to fully capture).
    my_application_status: str | None = None


class InternalJobApplicationCreate(BaseModel):
    note: str = Field(default="", max_length=1000)


class InternalJobApplicationOut(BaseModel):
    id: int
    posting_id: int
    applicant_name: str
    applicant_email: str
    note: str
    submitted_at: datetime
    status: str  # "approved" | "pending_approval" | "declined"
    decline_reason: str
    # Only populated by list_my_pending_approvals -- the admin-facing
    # applicants list already shows applications grouped under their
    # posting's own header, so the title would be redundant there.
    posting_title: str | None = None


class InternalJobApplicationDecision(BaseModel):
    approve: bool
    reason: str = Field(default="", max_length=1000)


class CertificationRequirementCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    content: str | None = Field(default=None, max_length=20000)
    department_id: int | None = None
    renewal_period_days: int | None = Field(default=None, ge=1, le=3650)


class CertificationRequirementOut(BaseModel):
    id: int
    name: str
    description: str
    content: str | None
    department_id: int | None
    department_name: str | None
    renewal_period_days: int | None
    created_at: datetime
    # Only populated on the employee-facing endpoint -- the admin
    # listing has no single "current employee" to check status
    # against, same has_applied/matches_your_goal pattern already used
    # for internal job postings.
    my_status: str | None = None  # "not_started" | "completed" | "expired" | None
    my_completed_at: datetime | None = None
    my_expires_at: datetime | None = None
    my_verified: bool | None = None


class EmployeeCertificationCreate(BaseModel):
    pass  # no body needed -- completing is just "I did this," the requirement_id is in the URL


class EmployeeCertificationOut(BaseModel):
    id: int
    application_id: int
    requirement_id: int
    applicant_name: str
    applicant_email: str
    completed_at: datetime
    expires_at: datetime | None
    verified_by_user_id: int | None
    verified_at: datetime | None


class DirectReportOut(BaseModel):
    """Aggregate-only progress summary for one of the current user's
    direct reports -- same privacy boundary as every other admin-
    facing view in this app: enrollment/progress numbers, never
    conversation content, never a career goal, never a meeting note.
    A manager is not necessarily an org admin; this is deliberately a
    third, narrower tier -- scoped to "people who report to me," not
    "everyone in my department" or "everyone in the company.\""""
    application_id: int
    user_full_name: str
    user_email: str
    department_name: str | None
    checklist_completion_pct: float
    mentor_name: str | None
    certifications_completed: int
    certifications_total: int
    certifications_expired: int


class MonthlyTrendPoint(BaseModel):
    """One month's worth of activity counts -- deliberately raw
    counts, not rates or percentages, since a rate needs a denominator
    that itself changes month to month (headcount grows over time) and
    would be misleading to compare directly across months without
    normalizing for that. Counts are always comparable as-is."""
    month: str  # "2026-08" format
    employees_joined: int
    checklist_completions: int
    mentor_meetings_logged: int
    certification_completions: int


class OrgAnalyticsTrends(BaseModel):
    points: list[MonthlyTrendPoint]  # oldest first


class OrgBenchmark(BaseModel):
    """Cross-organization, anonymized comparison -- same MIN_SAMPLE_SIZE
    discipline as rise_index.py's company_stats(): a benchmark only
    computes once enough OTHER orgs (not counting this one) have
    activity to average across, so no individual org's numbers could
    be reverse-engineered from a tiny comparison group. sample_size is
    always returned (so the UI can say how many orgs it's based on),
    but the averages themselves are None when below threshold."""
    sample_size: int
    your_checklist_completion_pct: float
    avg_checklist_completion_pct: float | None
    your_avg_meetings_per_pairing: float
    avg_meetings_per_pairing: float | None


class PulseCheckInOut(BaseModel):
    """The employee's own pending prompt to answer -- deliberately
    carries no prior sentiment/comment fields, since a pending
    check-in has neither yet."""
    id: int
    sent_at: datetime


class PulseCheckInRespond(BaseModel):
    sentiment: str = Field(pattern="^(great|okay|struggling)$")
    comment: str = Field(default="", max_length=2000)


class PulseSummary(BaseModel):
    """Aggregate-only, org-wide sentiment -- same 'counts and rates,
    never the actual words' principle as everywhere else. Sentiment
    percentages are None below MIN_PULSE_RESPONDENTS, same anonymity
    reasoning as OrgBenchmark's cross-org threshold, just scoped
    within one org: a 'great_pct: 100%' next to 'total_responded: 1'
    would functionally reveal exactly what that one person answered,
    which defeats the entire point of keeping sentiment aggregate-only
    in the first place."""
    period_days: int
    total_sent: int
    total_responded: int
    response_rate_pct: float
    great_pct: float | None
    okay_pct: float | None
    struggling_pct: float | None


class SuggestedMentorOut(BaseModel):
    contact_id: int
    name: str
    email: str
    mentor_bio: str
    score: int
    reason: str


class MentorMeetingLogCreate(BaseModel):
    meeting_date: date
    notes: str = Field(default="", max_length=2000)


class MentorMeetingFeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    feedback_note: str = Field(default="", max_length=1000)


class MentorMeetingLogOut(BaseModel):
    id: int
    mentor_assignment_id: int
    meeting_date: date
    notes: str
    rating: int | None
    feedback_note: str | None
    created_at: datetime


class MentorMeetingScheduleCreate(BaseModel):
    scheduled_at: datetime
    duration_minutes: int = Field(default=30, ge=5, le=480)


class MentorMeetingScheduleOut(BaseModel):
    id: int
    mentor_assignment_id: int
    scheduled_at: datetime
    duration_minutes: int
    calendar_event_created: bool  # True if a real invite went out, false if just saved
    cancelled_at: datetime | None
    created_at: datetime


class CareerGoalCreate(BaseModel):
    goal_text: str = Field(min_length=1, max_length=500)


class CareerGoalOut(BaseModel):
    id: int
    goal_text: str
    created_at: datetime
    achieved_at: datetime | None


class OrgEmployeeOut(BaseModel):
    application_id: int
    user_email: str
    user_full_name: str
    department_id: int | None
    department_name: str | None
    joined_at: datetime
    mentor_name: str | None
    mentor_assignment_id: int | None
    mentor_ended_at: datetime | None


# --- Knowledge base ---

class KBArticleCreate(BaseModel):
    category: str = Field(default="General", max_length=100)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=20000)


class KBArticleOut(BaseModel):
    id: int
    category: str
    title: str
    content: str
    updated_at: datetime

    class Config:
        from_attributes = True


class KBAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class KBAskResponse(BaseModel):
    answer: str
    sources: list[KBArticleOut]


# --- Support ---

class SupportContactRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=5000)


# --- Admin ---

class AdminBootstrapRequest(BaseModel):
    secret: str
    email: EmailStr


class AdminUserOut(BaseModel):
    id: int
    email: str
    full_name: str
    subscription_tier: str
    subscription_status: str
    is_admin: bool
    admin_role: str
    is_suspended: bool
    suspended_reason: str
    rise_points: int
    current_streak: int
    created_at: datetime

    class Config:
        from_attributes = True


class AdminSetRoleRequest(BaseModel):
    # "" removes admin access entirely. Otherwise one of super/support/billing/readonly.
    role: str = Field(default="", max_length=20)


class AdminSuspendRequest(BaseModel):
    reason: str = Field(default="", max_length=500)


class AdminRevenueOut(BaseModel):
    total_users: int
    free_count: int
    active_pro_count: int
    mrr_estimate_usd: float
    signups_this_week: int
    signups_this_month: int


class AdminUsageActionStat(BaseModel):
    count: int
    estimated_cost_usd: float


class AdminUsageOut(BaseModel):
    period: str
    by_action: dict[str, AdminUsageActionStat]
    total_estimated_cost_usd: float


class AdminFailureActionStat(BaseModel):
    action: str
    count: int


class AdminErrorsOut(BaseModel):
    period: str
    by_action: list[AdminFailureActionStat]
    total_failures: int


class AdminSupportMessageOut(BaseModel):
    id: int
    user_email: str
    subject: str
    message: str
    status: str
    admin_reply: Optional[str] = None
    replied_at: Optional[datetime] = None
    created_at: datetime


class AdminSupportReplyRequest(BaseModel):
    reply: str = Field(min_length=1, max_length=5000)


class CannedReplyCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)


class CannedReplyOut(BaseModel):
    id: int
    title: str
    body: str
    created_at: datetime

    class Config:
        from_attributes = True


# --- Admin: organizations ---

class AdminOrganizationOut(BaseModel):
    id: int
    name: str
    plan: str
    subscription_status: str
    included_seats: int
    member_count: int
    overage_seats: int
    estimated_mrr_usd: float
    created_at: datetime
    is_sandbox: bool = False


# --- Admin: system health ---

class AdminJobSourceHealthOut(BaseModel):
    source: str
    jobs_last_24h: int
    jobs_last_7d: int
    active_jobs: int = 0
    # Last time a discovery run saw this source's postings (not just added a
    # new one), so a steady source doesn't read as "silent".
    last_discovered_at: Optional[datetime] = None
    status: str  # "healthy" | "stale" | "silent"


class AdminDiscoverySourceRun(BaseModel):
    """What one source did in the most recent discovery run."""
    name: str
    status: str  # "ok" | "empty" | "failed" | "not_configured"
    fetched: int = 0
    new: int = 0
    detail: str = ""
    notes: list[str] = []


class AdminSystemHealthOut(BaseModel):
    job_sources: list[AdminJobSourceHealthOut]
    total_jobs_in_pool: int
    active_jobs_in_pool: int = 0
    # Plain-language problems that need an admin (a source switched off, ...).
    warnings: list[str] = []
    last_discovery_at: Optional[datetime] = None
    last_discovery_kind: str = ""
    last_discovery: list[AdminDiscoverySourceRun] = []


class AdminEmailFailure(BaseModel):
    kind: str
    to_addr: str
    subject: str
    status: str
    error: str = ""
    created_at: datetime


class AdminEmailHealthOut(BaseModel):
    configured: bool
    from_address: str
    sent_24h: int = 0
    failed_24h: int = 0
    skipped_24h: int = 0
    sent_7d: int = 0
    failed_7d: int = 0
    skipped_7d: int = 0
    recent_problems: list[AdminEmailFailure] = []


class AdminEmailTestOut(BaseModel):
    ok: bool
    to: str
    detail: str


# --- Admin: content moderation ---

class AdminFlaggedMessageOut(BaseModel):
    id: int
    application_id: int
    user_email: str
    role: str
    content: str
    flag_reason: str
    flag_resolved_at: Optional[datetime] = None
    created_at: datetime


# --- Admin: refunds ---

class AdminRefundRequest(BaseModel):
    reason: str = Field(default="", max_length=500)


# --- Rise Index ---

class CompanyStatsOut(BaseModel):
    company: str
    applied_count: int
    response_rate: int
    avg_days_to_respond: Optional[int] = None
    recent_applications: Optional[int] = None


class PointsEventOut(BaseModel):
    amount: int
    reason: str
    created_at: datetime

    class Config:
        from_attributes = True


class RiseIndexMeOut(BaseModel):
    rise_points: int
    current_streak: int
    longest_streak: int
    recent_events: list[PointsEventOut]


# --- Org Q&A ("Ghost Onboarder") ---

class OrgAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class OrgAskResponse(BaseModel):
    answer: str
    sources: list[str]


class OrgQALogOut(BaseModel):
    id: int
    application_id: int
    user_email: str
    question: str
    answer: str
    matched_content: bool
    created_at: datetime


# --- Culture Bot (spaced-repetition lessons) ---

class OrgLessonCreate(BaseModel):
    day_offset: int = Field(ge=0, le=365)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=5000)
    quiz_question: str = Field(default="", max_length=500)
    quiz_answer: str = Field(default="", max_length=200)
    department_id: Optional[int] = None
    order: int = 0
    media_url: str = Field(default="", max_length=2000)


class OrgLessonOut(BaseModel):
    id: int
    day_offset: int
    title: str
    content: str
    quiz_question: str
    quiz_answer: str
    department_id: Optional[int]
    order: int
    media_url: str = ""
    created_at: datetime


class LessonDeliveryOut(BaseModel):
    id: int
    lesson_id: int
    title: str
    content: str
    quiz_question: str
    media_url: str = ""
    delivered_at: datetime
    quiz_response: Optional[str] = None
    quiz_correct: Optional[bool] = None


class LessonQuizResponseRequest(BaseModel):
    response: str = Field(min_length=1, max_length=500)


# --- Browser extension: ad-hoc job scoring ---
# For a job the person is looking at directly on some external site,
# which may not exist anywhere in Riseply's own discovered job pool.

class ExtensionScoreRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    company: str = Field(min_length=1, max_length=200)
    location: str = Field(default="", max_length=200)
    description: str = Field(min_length=1, max_length=20000)


class ExtensionScoreResponse(BaseModel):
    score: int
    reason: str
    matched_profile: Optional[str] = None


class ExtensionAnswerQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=300)
    company: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20000)
    options: list[str] = Field(default_factory=list, max_length=100)


class ExtensionAnswerQuestionResponse(BaseModel):
    answer: str


class ExtensionCoverLetterRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    company: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20000)


class ExtensionCoverLetterResponse(BaseModel):
    cover_letter: str


# --- Multiple resumes, one marked default. Named "Saved*" specifically
# to avoid colliding with the pre-existing ResumeUpdate/ResumeParseOut
# above, which belong to the older single-resume-text PUT /me/resume
# flow and are unrelated to this feature. ---

class SavedResumeCreate(BaseModel):
    label: str = Field(default="", max_length=200)
    resume_text: str = Field(min_length=1, max_length=20000)


class SavedResumeUpdate(BaseModel):
    label: Optional[str] = Field(default=None, max_length=200)
    resume_text: Optional[str] = Field(default=None, min_length=1, max_length=20000)


class SavedResumeOut(BaseModel):
    id: int
    label: str
    resume_text: str
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True


# --- Org Buddy admin analytics ---

class ChecklistItemStats(BaseModel):
    item_id: int
    title: str
    total_assigned: int
    total_completed: int
    completion_rate: float


class LessonQuizStats(BaseModel):
    lesson_id: int
    title: str
    quiz_question: str
    total_attempts: int
    correct_count: int
    correct_rate: float


class QAGapStats(BaseModel):
    question: str
    count: int


class DepartmentStats(BaseModel):
    department_id: Optional[int]
    department_name: str
    total_employees: int
    completed_onboarding: int
    completion_rate: float


class MentorshipStats(BaseModel):
    """Aggregate-only, same privacy boundary as everything else in
    OrgAnalyticsOut -- counts and averages across pairings, never a
    per-pairing breakdown or any meeting note/feedback text."""
    total_pairings: int
    employees_with_mentor_pct: float
    total_meetings_logged: int
    avg_meetings_per_pairing: float
    avg_feedback_rating: Optional[float]  # None if no ratings submitted yet
    pairings_ended: int
    would_recommend_mentor_pct: Optional[float]  # None if no retrospectives submitted yet
    # Group/reciprocal relationships were shipped additive to 1:1
    # MentorAssignment (see MentorshipRelationship's own docstring) but
    # never got their own rollup here -- a known, explicitly documented
    # gap at the time. total_group_relationships and
    # total_reciprocal_relationships are separate counts (not summed)
    # since they're meaningfully different program shapes, the same
    # reasoning relationship_type stays a distinct field rather than a
    # generic "group" bucket everywhere else in this codebase.
    total_group_relationships: int
    total_reciprocal_relationships: int
    total_relationship_meetings_logged: int


class OrgAnalyticsOut(BaseModel):
    total_employees: int
    avg_days_to_complete_onboarding: Optional[float]
    checklist_items: list[ChecklistItemStats]
    lesson_quizzes: list[LessonQuizStats]
    qa_gaps: list[QAGapStats]
    departments: list[DepartmentStats]
    mentorship: MentorshipStats


# --- Discount codes ---

class DiscountCodeCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{3,30}$")
    kind: str = Field(pattern="^(stripe|free_days)$")
    percent_off: int | None = Field(default=None, ge=1, le=100)
    amount_off_cents: int | None = Field(default=None, ge=50, le=1_000_000)
    duration: str = Field(default="once", pattern="^(once|repeating|forever)$")
    duration_months: int | None = Field(default=None, ge=1, le=36)
    free_days: int | None = Field(default=None, ge=1, le=365)
    max_redemptions: int | None = Field(default=None, ge=1, le=1_000_000)
    expires_at: datetime | None = None
    note: str = Field(default="", max_length=200)

    @field_validator("expires_at")
    @classmethod
    def _naive_utc(cls, v):
        # Everything is stored as naive UTC; convert anything tz-aware.
        if v is not None and v.tzinfo is not None:
            from datetime import timezone
            v = v.astimezone(timezone.utc).replace(tzinfo=None)
        return v

    @model_validator(mode="after")
    def _check_shape(self):
        if self.kind == "stripe":
            if (self.percent_off is None) == (self.amount_off_cents is None):
                raise ValueError("Set either a percent off or a dollar amount off (not both).")
            if self.free_days is not None:
                raise ValueError("Free days only applies to free-days codes.")
            if self.duration == "repeating" and not self.duration_months:
                raise ValueError("Say how many months the discount lasts.")
            if self.duration != "repeating":
                self.duration_months = None
        else:
            if not self.free_days:
                raise ValueError("Say how many free Pro days this code grants.")
            if self.percent_off is not None or self.amount_off_cents is not None:
                raise ValueError("Free-days codes don't take a percent or amount off.")
            self.duration, self.duration_months = "once", None
        return self


class DiscountCodeActive(BaseModel):
    active: bool


class DiscountCodeOut(BaseModel):
    id: int
    code: str
    kind: str
    percent_off: int | None = None
    amount_off_cents: int | None = None
    duration: str = "once"
    duration_months: int | None = None
    free_days: int | None = None
    max_redemptions: int | None = None
    expires_at: datetime | None = None
    active: bool
    note: str = ""
    created_at: datetime
    redemption_count: int = 0
    status: str = "active"  # active | disabled | expired | exhausted
    description: str = ""


class DiscountRedemptionOut(BaseModel):
    email: str
    redeemed_at: datetime
    detail: str = ""


class DiscountCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=60)


class DiscountCodeCheckOut(BaseModel):
    valid: bool = True
    kind: str
    description: str


class SubscribeRequest(BaseModel):
    code: str | None = Field(default=None, max_length=60)


# --- Discord notifications ---

class DiscordConnectRequest(BaseModel):
    webhook_url: str = Field(min_length=20, max_length=300)
    timezone: str = Field(default="UTC", max_length=64)


class DiscordSettingsUpdate(BaseModel):
    enabled: bool | None = None
    nudge_enabled: bool | None = None
    progress_enabled: bool | None = None
    followup_enabled: bool | None = None
    matches_enabled: bool | None = None
    nudge_hour: int | None = Field(default=None, ge=0, le=23)
    timezone: str | None = Field(default=None, max_length=64)


class DiscordStatusOut(BaseModel):
    connected: bool = False
    webhook_hint: str = ""
    enabled: bool = False
    nudge_enabled: bool = True
    progress_enabled: bool = True
    followup_enabled: bool = True
    matches_enabled: bool = False
    nudge_hour: int = 18
    timezone: str = "UTC"
    last_error: str = ""
    last_success_at: datetime | None = None


# ---- Progress -------------------------------------------------------------

class ProgressScorePoint(BaseModel):
    session_id: int
    date: datetime
    target_role: str
    session_type: str
    topic: str
    score: int


class ProgressRole(BaseModel):
    target_role: str
    sessions: int
    scored: int
    first_score: Optional[int] = None
    latest_score: Optional[int] = None
    change: Optional[int] = None   # latest minus first, needs two scored sessions


class ProgressTopic(BaseModel):
    topic: str
    sessions: int
    avg_score: float


class ProgressPractice(BaseModel):
    sessions_completed: int
    sessions_in_progress: int
    scored_sessions: int
    avg_score: Optional[float] = None
    best_score: Optional[int] = None
    latest_score: Optional[int] = None
    change: Optional[int] = None   # recent scores vs the ones before them
    scores: list[ProgressScorePoint]
    by_role: list[ProgressRole]
    weakest_topics: list[ProgressTopic]
    notes_saved: int
    folders: int


class ProgressFunnel(BaseModel):
    matched: int
    approved: int
    applied: int
    interviewing: int
    offers: int


class ProgressWeek(BaseModel):
    week_start: date
    matches: int
    applied: int
    practice: int


class ProgressJobSearch(BaseModel):
    funnel: ProgressFunnel
    interview_rate: Optional[int] = None   # percent of applications that reached an interview
    weeks: list[ProgressWeek]


class ReadinessPart(BaseModel):
    session_type: str
    sessions: int
    score: Optional[int] = None   # average of the latest three scored sessions of this type


class ReadinessDimension(BaseModel):
    score: Optional[int] = None   # None until there is at least one scored session
    level: str                    # none | starting | building | close | ready
    sessions: int                 # scored sessions behind the score
    early: bool                   # fewer than 3 sessions: an early read, not a verdict
    parts: list[ReadinessPart]


class ReadinessRole(BaseModel):
    target_role: str
    scored_sessions: int
    get_job: ReadinessDimension
    do_job: ReadinessDimension
    next_type: str                # which kind of session would help most
    next_reason: str


class ProgressOut(BaseModel):
    readiness: list[ReadinessRole]
    practice: ProgressPractice
    job_search: ProgressJobSearch
    current_streak: int
    longest_streak: int
    rise_points: int


# ---- Feedback ---------------------------------------------------------------

FEEDBACK_CATEGORIES = ("idea", "problem", "praise")


class FeedbackIn(BaseModel):
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    category: str = ""
    message: str = Field(default="", max_length=2000)
    page: str = Field(default="", max_length=200)

    @field_validator("category")
    @classmethod
    def _category(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v and v not in FEEDBACK_CATEGORIES:
            raise ValueError("Choose idea, problem or praise.")
        return v

    @field_validator("message", "page")
    @classmethod
    def _strip(cls, v: str) -> str:
        return (v or "").strip()

    @model_validator(mode="after")
    def _something_to_say(self):
        if self.rating is None and not self.message:
            raise ValueError("Add a rating or a few words.")
        return self


class CoachReplyFeedbackIn(BaseModel):
    message_id: int
    helpful: bool
    note: str = Field(default="", max_length=1000)

    @field_validator("note")
    @classmethod
    def _strip(cls, v: str) -> str:
        return (v or "").strip()


class CoachReplyFeedbackOut(BaseModel):
    message_id: int
    helpful: bool


class AdminFeedbackOut(BaseModel):
    id: int
    user_email: str
    kind: str
    rating: Optional[int] = None
    helpful: Optional[bool] = None
    category: str = ""
    message: str = ""
    page: str = ""
    reply_excerpt: str = ""      # coach_reply: the coach's own reply that was rated
    status: str
    created_at: datetime


class AdminFeedbackSummary(BaseModel):
    total: int
    new: int
    avg_rating: Optional[float] = None       # general feedback, 1-5
    rated: int
    thumbs_up: int
    thumbs_down: int
