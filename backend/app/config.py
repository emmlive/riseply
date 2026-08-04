from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/agent.db"

    jwt_secret: str = "change-this-to-a-long-random-string"
    jwt_expire_minutes: int = 43200
    jwt_algorithm: str = "HS256"

    anthropic_api_key: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from_name: str = "Riseply"
    support_email: str = ""  # where "Contact support" messages get sent -- defaults to smtp_user if blank

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id_pro: str = ""  # a recurring monthly Price ID from your Stripe dashboard
    stripe_success_url: str = "http://localhost:3000/dashboard/billing?upgrade=success"
    stripe_cancel_url: str = "http://localhost:3000/dashboard/billing?upgrade=cancelled"
    stripe_portal_return_url: str = "http://localhost:3000/dashboard/billing"

    # --- Free tier limits (per user per calendar month) ---
    free_tier_max_matches_per_month: int = 50
    free_tier_max_tailored_resumes_per_month: int = 15
    free_tier_max_interview_preps_per_month: int = 10
    free_tier_max_onboarding_plans_per_month: int = 5
    free_tier_max_job_buddy_messages_per_month: int = 60
    free_tier_max_search_profiles: int = 1

    # --- Pro tier limits ---
    pro_tier_max_matches_per_month: int = 300
    pro_tier_max_tailored_resumes_per_month: int = 100
    pro_tier_max_interview_preps_per_month: int = 50
    pro_tier_max_onboarding_plans_per_month: int = 30
    pro_tier_max_job_buddy_messages_per_month: int = 500
    pro_tier_max_search_profiles: int = 10

    allowed_origins: str = "http://localhost:3000"

    class Config:
        env_file = ".env"

    @property
    def allowed_origins_list(self):
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
