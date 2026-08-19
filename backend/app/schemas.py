from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


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


# --- Applications ---

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
    tailoring_rationale: str = ""
    has_tailored_resume_data: bool = False

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


class OrgSettingsUpdate(BaseModel):
    logo_url: str = Field(default="", max_length=1000)


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


class OrgContentOut(BaseModel):
    id: int
    title: str
    content: str
    department_id: int | None
    media_url: str = ""
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


class OrgContactOut(BaseModel):
    id: int
    name: str
    email: str
    description: str
    department_id: int | None
    is_mentor: bool
    created_at: datetime


class HandoffRequestCreate(BaseModel):
    contact_id: int
    note: str = Field(min_length=1, max_length=2000)


class MentorAssignRequest(BaseModel):
    contact_id: int


class MentorAssignmentOut(BaseModel):
    id: int
    name: str
    email: str
    description: str
    assigned_at: datetime


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
    last_discovered_at: Optional[datetime] = None
    status: str  # "healthy" | "stale" | "silent"


class AdminSystemHealthOut(BaseModel):
    job_sources: list[AdminJobSourceHealthOut]
    total_jobs_in_pool: int


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


class OrgAnalyticsOut(BaseModel):
    total_employees: int
    avg_days_to_complete_onboarding: Optional[float]
    checklist_items: list[ChecklistItemStats]
    lesson_quizzes: list[LessonQuizStats]
    qa_gaps: list[QAGapStats]
    departments: list[DepartmentStats]
