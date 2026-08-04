# Riseply — multi-user job search web app

A public, multi-tenant job application agent: anyone can sign up, add
their resume, run several search profiles at once, and review matches
before anything is submitted. Built as two services:

- **`backend/`** — FastAPI + SQLAlchemy (Python). Auth, per-user search
  profiles, job matching/resume tailoring via the Claude API, usage
  metering with free/Pro tiers, Stripe subscriptions + tips.
- **`frontend/`** — Next.js (TypeScript, App Router). Dashboard UI —
  no code editing needed to add/change search profiles, unlike the
  original CLI version.

## Architecture

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────┐
│  Next.js    │ HTTP │  FastAPI backend  │      │  Postgres   │
│  frontend   │◄────►│  (auth, profiles, │◄────►│  (Neon)     │
│  (Cloudflare│      │   matching, tips) │      │             │
│   Pages)    │      │   (Render)        │      └─────────────┘
└─────────────┘      └────────┬─────────┘
                               │
                               ▼
                      ┌──────────────────┐
                      │  Claude API      │  job matching +
                      │  (Anthropic)     │  resume tailoring
                      └──────────────────┘
```

Each user has their own resume, search profiles, and applications
(isolated by `user_id`). Discovered job postings are shared across all
users — the same posting is relevant to anyone searching for it — but
matching, tailoring, and application status are all per-user.

## Local setup

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY, JWT_SECRET, SMTP creds
uvicorn app.main:app --reload --port 8000
```

The database (SQLite by default, at `backend/data/agent.db`) is created
automatically on first run — no separate migration step needed for local
dev.

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # points at http://localhost:8000 by default
npm run dev
```

Visit `http://localhost:3000`, sign up, add a resume and a search profile,
then hit **Find new matches** on the Overview page.

## Deploying

**Recommended stack:** Cloudflare Pages (frontend, free) + Render
(backend + Postgres, free tier). The frontend ships as a static export —
no server-side API routes exist in this app, since every data call goes
to the FastAPI backend — so Cloudflare Pages serves it directly with no
adapter needed.

> **Why not the backend too?** Cloudflare Workers' Python runtime is
> WASM-based (Pyodide) and can't run this backend's native dependencies —
> `bcrypt`, `psycopg2`, and parts of SQLAlchemy all need real compiled
> code. Running the backend on Render and the frontend on Cloudflare is
> the practical split.

### 1. Database (Neon) + backend on Render

This app uses [Neon](https://neon.tech) for Postgres rather than Render's
own database offering — free tier, scales to zero when idle.

- Create a Neon project, copy the connection string it gives you
  (`postgresql://user:pass@ep-....neon.tech/neondb?sslmode=require`).
- On Render: **New → Web Service** → connect this repo → **Root
  directory**: `backend` → **Build command**: `pip install -r
  requirements.txt` → **Start command**: `uvicorn app.main:app --host
  0.0.0.0 --port $PORT`.
- Set env vars: `DATABASE_URL` (the Neon string above), `JWT_SECRET`
  (generate with `python -c "import secrets; print(secrets.token_hex(32))"`),
  `ANTHROPIC_API_KEY`, and SMTP vars if you want email notifications live.
  Leave `ALLOWED_ORIGINS` for step 3.
- Once deployed, copy the backend's URL (looks like
  `https://riseply.onrender.com`).

A `render.yaml` Blueprint is also included at the repo root as a faster
alternative for redeploying from scratch — it defines the same service
and env vars (with `DATABASE_URL` left for you to fill in manually,
since it's an external Neon database rather than something Render
provisions itself).

### 2. Frontend on Cloudflare Pages, with your domain already in Cloudflare

Since `riseply.com` is already registered through Cloudflare, connecting
it is simpler than a domain bought elsewhere — same account, same
dashboard, no separate DNS provider to configure.

- Push this repo to GitHub if you haven't (already done if you're
  reading this from there).
- In the Cloudflare dashboard: **Workers & Pages → Create → Pages →
  Connect to Git**, select this repo.
- Build settings:
  - Framework preset: **Next.js (Static HTML Export)**
  - Build command: `npm run build`
  - Build output directory: `out`
  - Root directory: `frontend`
- Environment variable: `NEXT_PUBLIC_API_URL` = your Render backend URL
  from step 1.
- Deploy. You'll get a free `riseply.pages.dev` URL first — that's
  expected, the custom domain attaches next.
- **Attach `riseply.com`**: in the Pages project → **Custom domains** →
  **Set up a custom domain** → enter `riseply.com`. Because the domain's
  already in the same Cloudflare account, this is just a confirmation
  click — Cloudflare adds the DNS record for you automatically, no
  manual CNAME needed. Do the same for `www.riseply.com` if you want
  that to work too.

### 3. Close the loop: CORS

Go back to Render → your backend service → **Environment** →
set `ALLOWED_ORIGINS` to `https://riseply.com` (and
`https://riseply.pages.dev` too, useful for testing before DNS
propagates) → save, which triggers a redeploy. Skipping this step is
the most common reason a freshly deployed frontend can't talk to its
backend — every request will fail CORS until this is set.

### 4. Stripe — subscriptions (Pro plan) and tips

Riseply has two Stripe integrations: a real recurring **Pro subscription**
and an optional one-off **tip**. Both share `STRIPE_SECRET_KEY`; the
subscription needs two more things set up.

1. **Get your secret key**: [dashboard.stripe.com/apikeys](https://dashboard.stripe.com/apikeys)
   → set `STRIPE_SECRET_KEY` on Render. Use a `sk_test_...` key while
   testing, switch to `sk_live_...` when you're ready for real payments.
2. **Create the Pro plan as a Stripe Product**: Stripe dashboard →
   **Product catalog** → **Add product** → give it a recurring monthly
   price (the app suggests $9.99/mo, but that's just a UI label — the
   actual price is whatever you set here). Copy the resulting **Price
   ID** (`price_...`) → set it as `STRIPE_PRICE_ID_PRO` on Render.
3. **Set up the webhook** — this is what actually flips a user to Pro
   after they pay, so don't skip it: Stripe dashboard → **Developers →
   Webhooks** → **Add endpoint** → URL is
   `https://your-backend.onrender.com/billing/webhook` → select these
   events: `checkout.session.completed`, `customer.subscription.updated`,
   `customer.subscription.deleted` → save, then copy the **signing
   secret** shown → set it as `STRIPE_WEBHOOK_SECRET` on Render.

Without `STRIPE_WEBHOOK_SECRET` set, the webhook endpoint still works but
skips signature verification — fine for local testing, **not safe for
production**, since anyone could POST a fake "payment succeeded" event
without it.

Until `STRIPE_SECRET_KEY` is set at all, both the upgrade button and the
tip button return a clear "not configured yet" response instead of
failing silently.

## Pricing tiers

| | Free | Pro |
|---|---|---|
| Job matches / month | 50 | 300 |
| Resumes tailored / month | 15 | 100 |
| Interview preps / month | 10 | 50 |
| Onboarding plans / month | 5 | 30 |
| Job Buddy messages / month | 60 | 500 |
| Simultaneous search profiles | 1 | 10 |

All of these are configurable via env vars (`FREE_TIER_*` /
`PRO_TIER_*` in `.env.example`) without touching code. A user's tier is
never trusted from the client — it's set exclusively by the Stripe
webhook handler based on actual subscription status, so there's no way
to spoof Pro access from the frontend.

## Admin dashboard

Available at `/dashboard/admin` for any account with `is_admin = true`.
Covers revenue (estimated MRR, active Pro count, signup trends), usage
and estimated Claude API cost broken down by action, a real error-rate
signal (hooks into the exact point where a metered Claude call already
fails, not a synthetic metric), a user list, and an in-app support
inbox (reply to a message and it emails the user directly).

**Creating your first admin** — there's a chicken-and-egg problem since
no UI exists to promote someone before an admin exists:
1. Set `ADMIN_BOOTSTRAP_SECRET` on the backend (generate with
   `python -c "import secrets; print(secrets.token_hex(24))"`).
2. Sign up a normal account, then call the bootstrap endpoint once:
   ```bash
   curl -X POST https://your-backend.onrender.com/admin/bootstrap \
     -H "Content-Type: application/json" \
     -d '{"secret": "your-bootstrap-secret", "email": "you@example.com"}'
   ```
3. Log out and back in (or just refresh) — the Admin link appears in
   the sidebar. Consider unsetting `ADMIN_BOOTSTRAP_SECRET` afterward,
   or at least rotating it, since it's a standing credential that can
   promote any account to admin as long as it's set.

Revenue and cost numbers are estimates (`PRO_PRICE_USD_DISPLAY` for
MRR, rough per-call token estimates for API cost) — real source of
truth for money is always Stripe.

## Known gaps / next steps

- **Job Buddy currently requires going through Riseply's own matching
  pipeline to reach 'accepted' status.** Someone who already has a job
  and just wants the onboarding mentor has no way in yet — needs a
  manual "add a job I already have" entry point that skips discovery/
  matching and creates an application straight at 'accepted'.
- **No resource library / career content yet** (resume guides, interview
  skill articles, negotiation tips) — flagged as a growth/content lever,
  not yet built.
- **Discovery sources are a fixed list** (`backend/app/services/discovery_sources.py`)
  rather than admin-editable from the UI. Fine for a v1; a future
  improvement would be an admin panel for managing these.
- **Auto-submit (Playwright form-filling) isn't wired into the web app
  yet.** The original CLI version had it; bringing it to a multi-user web
  app needs a background worker (submitting a form mid-HTTP-request
  doesn't fit the request/response model), which is a real chunk of
  additional work — plan for a task queue (e.g. Celery + Redis, or a
  simpler polling worker) before building this out. Until then,
  "Approve" marks an application ready, and actually applying still
  needs to happen manually via the "View posting" link — which,
  practically, is also the safer default given job platforms' Terms of
  Service around automated submissions at scale.
- **Auth is hand-rolled** (JWT + bcrypt) rather than a managed provider.
  This was tested and works correctly, but for a real public launch with
  real user data, consider migrating to Clerk, Auth.js, or Supabase Auth
  — they handle things like password-reset flows, email verification,
  and abuse detection that this MVP doesn't.
- **No email verification or password reset flow yet.**
