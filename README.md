# Job Agent — multi-user web app

A public, multi-tenant version of the job application agent: anyone can
sign up, add their resume, run several search profiles at once, and review
matches before anything is submitted. Built as two services:

- **`backend/`** — FastAPI + SQLAlchemy (Python). Auth, per-user search
  profiles, job matching/resume tailoring via the Claude API, usage
  metering, Stripe tips.
- **`frontend/`** — Next.js (TypeScript, App Router). Dashboard UI —
  no code editing needed to add/change search profiles, unlike the
  original CLI version.

## Architecture

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────┐
│  Next.js    │ HTTP │  FastAPI backend  │      │  Postgres/  │
│  frontend   │◄────►│  (auth, profiles, │◄────►│  SQLite     │
│  (Vercel)   │      │   matching, tips) │      │  (Supabase/ │
└─────────────┘      └────────┬─────────┘      │  Railway)   │
                               │                └─────────────┘
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

**Recommended stack:** Vercel (frontend) + Railway or Render (backend) +
Supabase or Neon (Postgres). All have workable free tiers, and this is
exactly the setup the code is built to swap into — the app itself doesn't
change between local SQLite and hosted Postgres.

1. **Database**: create a Postgres instance on Supabase/Neon/Railway, copy
   its connection string.
2. **Backend**: deploy `backend/` to Railway/Render.
   - Set `DATABASE_URL` to the Postgres connection string (this is the
     *only* change needed to move off SQLite — same SQLAlchemy code runs
     against either).
   - Set `JWT_SECRET` to a long random value (generate with
     `python -c "import secrets; print(secrets.token_hex(32))"`)
   - Set `ANTHROPIC_API_KEY`, SMTP credentials, and `ALLOWED_ORIGINS` to
     your deployed frontend's URL.
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. **Frontend**: deploy `frontend/` to Vercel.
   - Set `NEXT_PUBLIC_API_URL` to your deployed backend's URL.
4. **Stripe (tips)**: create a Stripe account, grab the secret key from the
   dashboard, set `STRIPE_SECRET_KEY` on the backend. Until you do, the
   tip endpoint returns a clear "not configured yet" response instead of
   failing silently.

## Known gaps / next steps

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
- **Usage limits are simple monthly counters**, configurable via
  `.env` (`FREE_TIER_MAX_MATCHES_PER_MONTH`,
  `FREE_TIER_MAX_TAILORED_RESUMES_PER_MONTH`). No paid tier with higher
  limits yet — that's a natural next step once tips validate there's
  interest, using Stripe Billing subscriptions instead of one-off
  Checkout sessions.
