from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/agent.db"

    jwt_secret: str = "change-this-to-a-long-random-string"
    jwt_expire_minutes: int = 43200
    jwt_algorithm: str = "HS256"

    frontend_url: str = "http://localhost:3000"
    password_reset_expire_minutes: int = 30

    # Cloudflare Turnstile (CAPTCHA on signup). Leave blank to disable --
    # signup works normally without it, just with no bot protection.
    turnstile_secret_key: str = ""

    # --- OAuth sign-in (Google, Microsoft) ---
    # Client secrets are backend-only, never sent to the frontend. The
    # client IDs ARE also needed on the frontend (not secret, safe to
    # expose) via NEXT_PUBLIC_GOOGLE_CLIENT_ID / NEXT_PUBLIC_MICROSOFT_CLIENT_ID
    # -- keep those in sync with these if you change them.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    microsoft_oauth_client_id: str = ""
    microsoft_oauth_client_secret: str = ""
    # Frontend base URL, used to build the redirect_uri sent to Google/
    # Microsoft during token exchange -- must exactly match what's
    # registered in each provider's app console AND what the frontend
    # actually redirected from.
    oauth_frontend_base_url: str = "http://localhost:3000"

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

    # Estimate only, used for the admin MRR display -- the real price
    # lives in Stripe (STRIPE_PRICE_ID_PRO). Keep this in sync manually
    # if you change the price in Stripe's dashboard.
    pro_price_usd_display: float = 9.99

    # One-time admin bootstrap: POST /admin/bootstrap with this secret
    # promotes an account to admin. There's no UI path to create the
    # first admin otherwise. Generate a long random value and treat it
    # like any other credential -- rotate/unset it once you've used it.
    admin_bootstrap_secret: str = ""

    # --- Scheduled matching (external cron trigger) ---
    # A shared secret the external scheduler sends as X-Cron-Secret.
    # Blank means the endpoint is disabled (503), not open -- there's no
    # "unauthenticated batch job that processes every user" default.
    cron_secret: str = ""

    # --- Org Buddy as a Service: hybrid pricing (base plan + overage) ---
    # Real prices live in Stripe (like the individual Pro plan) -- these
    # are display/reference values and the included-seat counts used to
    # detect overage. Update to match whatever's actually configured in
    # Stripe's dashboard.
    org_plan_starter_price_usd: float = 199.0
    org_plan_starter_seats: int = 10
    org_plan_growth_price_usd: float = 599.0
    org_plan_growth_seats: int = 50
    org_plan_overage_price_per_seat_usd: float = 8.0
    # Stripe Price IDs for each plan's base subscription -- set these once
    # you've created the recurring Prices in Stripe's dashboard.
    stripe_price_id_org_starter: str = ""
    stripe_price_id_org_growth: str = ""
    # Global kill-switch. Defaults OFF -- must be explicitly enabled, and
    # even then only ever fires on an application the user has already
    # approved, and only against domains in the allowlist below.
    auto_submit_enabled: bool = False
    # Comma-separated list of domains auto-submit is allowed to touch.
    # Deliberately an ALLOWLIST, not a blocklist -- LinkedIn, Indeed, and
    # everything else are blocked by default, not just discouraged.
    #
    # Workday and iCIMS are deliberately NOT included, even though
    # they're extremely common ATS platforms: Workday requires creating
    # a per-tenant account through a multi-step wizard and has documented
    # bot detection that blocks naive automation; iCIMS forms are often
    # multi-step, frequently require login, and use custom JS-driven
    # inputs that can block standard form-filling. Both would need a
    # meaningfully more sophisticated (and riskier) automation approach
    # than the single-page form-fill this app does today.
    auto_submit_allowed_domains: str = "boards.greenhouse.io,job-boards.greenhouse.io,jobs.lever.co,jobs.ashbyhq.com,apply.workable.com"

    @property
    def auto_submit_allowed_domains_list(self) -> list[str]:
        return [d.strip().lower() for d in self.auto_submit_allowed_domains.split(",") if d.strip()]

    # --- Free tier limits (per user per calendar month) ---
    free_tier_max_matches_per_month: int = 50
    free_tier_max_tailored_resumes_per_month: int = 15
    free_tier_max_interview_preps_per_month: int = 10
    free_tier_max_onboarding_plans_per_month: int = 5
    free_tier_max_job_buddy_messages_per_month: int = 60
    free_tier_max_org_ask_per_month: int = 100
    free_tier_max_search_profiles: int = 1

    # --- Pro tier limits ---
    pro_tier_max_matches_per_month: int = 300
    pro_tier_max_tailored_resumes_per_month: int = 100
    pro_tier_max_interview_preps_per_month: int = 50
    pro_tier_max_onboarding_plans_per_month: int = 30
    pro_tier_max_job_buddy_messages_per_month: int = 500
    pro_tier_max_org_ask_per_month: int = 500
    pro_tier_max_search_profiles: int = 10

    # --- Culture Bot (spaced-repetition onboarding lessons) ---
    # Shared secret for the external scheduler that triggers the daily
    # delivery run -- same pattern as admin_bootstrap_secret, since this
    # endpoint has to be callable without an interactive user login.
    culture_bot_cron_secret: str = ""

    allowed_origins: str = "http://localhost:3000"

    class Config:
        env_file = ".env"

    @property
    def allowed_origins_list(self):
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
