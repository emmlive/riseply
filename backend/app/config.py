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

    # --- Calendar sync (Microsoft Graph / Google Calendar) ---
    # Deliberately separate from the OAuth settings above: login OAuth
    # exchanges a code once, reads the person's identity, and discards
    # the token -- it never needs to be reusable. Calendar access needs
    # a token that's usable again days or weeks later to create/cancel
    # events, so it gets persisted (encrypted -- see
    # services/calendar_encryption.py) rather than thrown away.
    # Same Microsoft Graph app registration as login can be reused here
    # by adding the Calendars.ReadWrite scope to its consent -- this
    # doesn't require a second app registration in Azure, just a
    # broader scope requested at connect time.
    calendar_token_encryption_key: str = ""

    anthropic_api_key: str = ""

    # --- Job discovery: Adzuna (general, all-industries keyword search) ---
    # Empty by default -- same kill-switch pattern as every other optional
    # integration (Resend, Twilio, Stripe). Until both are set,
    # sources/adzuna.py no-ops and discovery falls back to just the fixed
    # Greenhouse/Lever/RSS sources in discovery_sources.py. Free at
    # https://developer.adzuna.com/ -- register for an app_id/app_key pair.
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    # Adzuna's free tier is roughly 1,000 calls/month; one call = one
    # keyword's worth of results. This bounds how many DISTINCT search-
    # profile titles get queried in a single discovery run so a run with
    # many active profiles across many users can't burn the whole
    # monthly quota at once -- see pipeline_runner.run_discovery() for
    # how the remainder rotate in on subsequent runs instead of being
    # dropped entirely.
    adzuna_max_keywords_per_run: int = 15
    # Bounds the SEPARATE location-paired query batch (title x location,
    # via Adzuna's `where` filter) -- additive to the broad keyword-only
    # batch above, not a replacement for it. Kept smaller since it's
    # extra call volume on top of the existing budget; see
    # pipeline_runner._collect_active_location_hints() for why this
    # exists (narrow-location profiles were under-served by a purely
    # national keyword search).
    adzuna_max_location_pairs_per_run: int = 10
    # How many result pages to pull per keyword (50 results/page).
    # Directly multiplies call volume against the monthly quota --
    # (keywords_per_run + location_pairs_per_run) * pages_per_keyword
    # = calls per discovery run. Was hardcoded at 1; raised to 2 by
    # default for meaningfully wider coverage per keyword/location
    # pair, at roughly double the call cost per run. Tune down if
    # actual monthly usage is running close to Adzuna's ~1,000
    # call/month free-tier limit.
    adzuna_pages_per_keyword: int = 2

    # --- Job discovery: USAJobs (US federal jobs, keyword search) ---
    # Empty by default -- same kill-switch pattern as Adzuna above.
    # Until both are set, sources/usajobs.py no-ops. Free at
    # https://developer.usajobs.gov/apirequest/ -- register with an
    # email address and receive an Authorization-Key by return email.
    # Unlike most APIs, the registered EMAIL itself is required on
    # every request (as the User-Agent header, not a browser string --
    # USAJobs' own docs note this inverted convention trips people up)
    # alongside the key, so both need to be stored, not just the key.
    usajobs_api_key: str = ""
    usajobs_email: str = ""
    # USAJobs doesn't publish an explicit rate limit the way Adzuna
    # does, but it's rate-limited per User-Agent string regardless --
    # same bounding pattern as Adzuna's keyword cap so a run with many
    # active search profiles can't hammer it, and so the remainder
    # rotate in on subsequent runs (see
    # pipeline_runner._select_keyword_rotation(), reused here rather
    # than duplicated).
    usajobs_max_keywords_per_run: int = 15
    # USAJobs supports up to 500 results/page (far higher than
    # Adzuna's 50) -- kept modest here since this is per KEYWORD, and
    # federal listings for a single title are usually a much smaller,
    # more specific pool than a general commercial job board's.
    usajobs_results_per_page: int = 50

    # --- Email (Resend) ---
    # Empty by default -- same kill-switch pattern as every other
    # optional integration (Stripe, Twilio, CRON_SECRET). Until
    # RESEND_API_KEY is set, send_email() prints and skips instead of
    # sending. Switched from raw SMTP because Render's free tier blocks
    # outbound SMTP ports (25/465/587) entirely at the network level --
    # no SMTP_HOST/PORT/USER/PASS combination can work around that, so
    # this uses Resend's HTTPS API instead (port 443, never blocked).
    resend_api_key: str = ""
    # Must be on a domain verified in the Resend dashboard (riseply.com)
    # -- Resend rejects sends from unverified domains.
    resend_from_email: str = "support@riseply.com"
    resend_from_name: str = "Riseply"
    support_email: str = ""  # where "Contact support" messages get sent -- defaults to resend_from_email if blank

    # --- SMS (Twilio) ---
    # Empty by default, same kill-switch pattern as SMTP above -- until
    # all three are set, sms.send_sms() prints and skips instead of
    # sending, exactly like send_email() does when SMTP is unset. Get
    # these from the Twilio console after setting up an account and a
    # phone number capable of sending SMS (needs A2P 10DLC registration
    # for US numbers before messages reliably deliver at any volume).
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

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

    # How many unseen jobs a single interactive "Find new matches" click
    # scores before returning, so the request comes back in a reasonable
    # time regardless of the user's monthly limit or pool size. The
    # scheduled batch job isn't capped -- it works through the rest
    # overnight without anyone waiting on it.
    #
    # Tier-differentiated (previously a single shared manual_match_run_
    # job_cap=25 for everyone) so Pro is a genuinely deeper search per
    # click, not just more monthly clicks at the same depth -- a felt
    # reason to upgrade, not just a higher number on a usage meter
    # nobody's watching in the moment.
    free_tier_match_run_job_cap: int = 40
    pro_tier_match_run_job_cap: int = 100
    # A new user's very first "Find new matches" click (see
    # models.User.used_welcome_search) scores this many instead of
    # their tier's normal per-click cap, and doesn't consume any of
    # the monthly match quota at all -- see routers/pipeline.py. The
    # goal is a strong first impression, and for a free-tier user, a
    # real preview of what Pro-depth search feels like.
    welcome_search_job_cap: int = 100


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
    free_tier_max_search_profiles: int = 2

    # --- Pro tier limits ---
    pro_tier_max_matches_per_month: int = 300
    pro_tier_max_tailored_resumes_per_month: int = 100
    pro_tier_max_interview_preps_per_month: int = 50
    pro_tier_max_onboarding_plans_per_month: int = 30
    pro_tier_max_job_buddy_messages_per_month: int = 500
    pro_tier_max_org_ask_per_month: int = 500
    pro_tier_max_search_profiles: int = 10

    # --- Culture Bot (spaced-repetition onboarding lessons) ---
    # Reuses cron_secret (above) -- both scheduled jobs are triggered the
    # same way (GitHub Actions -> /internal/*), so one shared secret is
    # simpler to set up than a second one.

    allowed_origins: str = "http://localhost:3000"

    class Config:
        env_file = ".env"

    @property
    def allowed_origins_list(self):
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
