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

    stripe_secret_key: str = ""
    stripe_success_url: str = "http://localhost:3000/dashboard?tip=success"
    stripe_cancel_url: str = "http://localhost:3000/dashboard?tip=cancelled"

    free_tier_max_matches_per_month: int = 50
    free_tier_max_tailored_resumes_per_month: int = 15
    free_tier_max_interview_preps_per_month: int = 10
    free_tier_max_onboarding_plans_per_month: int = 5
    free_tier_max_job_buddy_messages_per_month: int = 60

    allowed_origins: str = "http://localhost:3000"

    class Config:
        env_file = ".env"

    @property
    def allowed_origins_list(self):
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
