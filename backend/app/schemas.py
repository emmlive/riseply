from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


# --- Auth ---

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = ""
    agree_to_terms: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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


# --- Search profiles ---

class SearchProfileIn(BaseModel):
    name: str
    titles: list[str] = []
    locations: list[str] = []
    seniority: list[str] = []
    min_match_score: int = 70
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
