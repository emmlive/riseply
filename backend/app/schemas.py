from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


# --- Auth ---

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = ""
    agree_to_terms: bool = False
    captcha_token: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


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
    resume_text: str
    subscription_tier: str
    subscription_status: str
    is_admin: bool

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
    rise_points: int
    current_streak: int
    created_at: datetime

    class Config:
        from_attributes = True


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
