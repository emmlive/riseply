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

## Scheduled matching

"Find new matches" on the Overview page is a manual click by default —
there's no background job running inside the web process. Render's free
tier spins down after ~15 min idle, so an in-process scheduler wouldn't
reliably run anyway; the practical fix is an external trigger hitting a
protected batch endpoint.

**Setup (free, via GitHub Actions):**
1. Generate a secret: `python -c "import secrets; print(secrets.token_hex(24))"`
2. Set it as `CRON_SECRET` on Render.
3. Add two repo secrets on GitHub (Settings → Secrets and variables →
   Actions): `CRON_SECRET` (same value) and `BACKEND_URL` (your Render
   backend URL, no trailing slash).
4. That's it — `.github/workflows/daily-matching.yml` is already in this
   repo and will run automatically at 13:00 UTC daily. Adjust the cron
   schedule in that file to whatever time works for you, or trigger it
   manually any time from the Actions tab ("Run workflow" button).

The endpoint itself (`POST /internal/scheduled-run`) is disabled (503)
until `CRON_SECRET` is set — there's no "unauthenticated batch job that
processes every user" default. It runs discovery once, then matching for
every user who has a resume and at least one active search profile,
skipping everyone else without erroring.

## Signup abuse protection

Two independent layers, both optional and both degrade gracefully when
unconfigured (signup works normally either way):

**Rate limiting** — always on, no setup needed: 5 signups/hour, 15
logins/hour, 5 password-reset requests/hour, 10 password-reset
completions/hour, all keyed per IP address (reads `X-Forwarded-For`
correctly behind Render's proxy, not just the raw connection IP, which
would otherwise make every visitor look identical).

**CAPTCHA (Cloudflare Turnstile)** — off by default, needs setup:
1. Cloudflare dashboard → Turnstile → **Add site**, point it at your
   domain.
2. Copy the **Site Key** → set `NEXT_PUBLIC_TURNSTILE_SITE_KEY` on
   Cloudflare Pages.
3. Copy the **Secret Key** → set `TURNSTILE_SECRET_KEY` on Render.

**Important**: these two need to be set together. If you set the
backend secret without the frontend site key, every signup breaks — the
backend will require a CAPTCHA token but the frontend never shows a
widget to produce one. Setting only the frontend key is harmless (just
an unused widget); the backend simply skips verification until its own
key is set.

## OAuth sign-in (Google, Microsoft)

Off by default — the "Continue with Google/Microsoft" buttons on
login/signup simply don't render until configured, same graceful-
degradation pattern as CAPTCHA above.

**Architecture**: the frontend redirects the browser directly to
Google's/Microsoft's own authorization page (using the client ID,
which isn't secret) with a random `state` value stored in
`sessionStorage` first. When the provider redirects back to
`/oauth-callback/{google,microsoft}` with a `code`, the frontend
verifies the returned `state` matches what it stored *before* doing
anything else — a mismatch means the request wasn't legitimately
initiated by this browser, and the backend is never even called in
that case (verified directly: sent a callback with a deliberately
wrong state and confirmed zero backend calls happened). Only after
that check passes does the frontend POST the `code` to the backend,
which does the actual token exchange server-side using the client
secret — the secret never reaches the browser, and the resulting JWT
comes back in a JSON response body rather than sitting in a URL where
it could end up in browser history or server logs.

**Account linking**: signing in with an email that already has a
password-based Riseply account logs into that same account rather than
creating a duplicate (verified directly — created a password account,
signed in via mocked Google OAuth with the same email, confirmed it
resolved to the same user ID with exactly one row for that email).
New accounts created via OAuth get a random, cryptographically
unguessable password hash rather than a nullable password column —
deliberately minimal-blast-radius: the existing password-login code
path needed zero changes, and if someone wants password access later,
the existing "forgot password" flow already handles setting a real one
for any account regardless of how it was created.

**Setup**:
1. **Google**: [Google Cloud Console](https://console.cloud.google.com/apis/credentials) →
   create an OAuth 2.0 Client ID (Web application) → add
   `https://riseply.com/oauth-callback/google` as an authorized redirect
   URI → copy the Client ID and Client Secret.
2. **Microsoft**: [Azure Portal](https://portal.azure.com) → App registrations →
   New registration → add `https://riseply.com/oauth-callback/microsoft`
   as a Web redirect URI → under "Certificates & secrets," create a
   client secret → copy the Application (client) ID and the secret.
3. Set `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` and/or
   `MICROSOFT_OAUTH_CLIENT_ID` / `MICROSOFT_OAUTH_CLIENT_SECRET` on
   Render, plus `OAUTH_FRONTEND_BASE_URL` (e.g. `https://riseply.com`).
4. Set the matching `NEXT_PUBLIC_GOOGLE_CLIENT_ID` /
   `NEXT_PUBLIC_MICROSOFT_CLIENT_ID` (client ID only, not the secret) on
   Cloudflare Pages.

Rate-limited the same way as signup/login (10 attempts/hour per IP).

## Auto-submit

Fills and (optionally) submits a job application via Playwright browser
automation, restricted to an explicit allowlist of ATS platforms. This
is **off by default** and needs deliberate setup — nothing about it
runs unless you turn it on.

**Guardrails, all independently tested:**
- Global kill-switch (`AUTO_SUBMIT_ENABLED=false` by default) — the
  endpoint returns a clean 503 until this is explicitly set to `true`.
- Allowlist, not a blocklist: only fires on domains in
  `AUTO_SUBMIT_ALLOWED_DOMAINS` — defaults to Greenhouse, Lever, Ashby,
  and Workable. LinkedIn and Indeed are hard-blocked in code regardless
  of that setting, as defense in depth.
- Only ever runs on an application the user has already approved — this
  never touches a job the user hasn't reviewed.
- Every outcome (submitted / needs manual review / failed) leaves the
  application in a recoverable state with a clear note — a CAPTCHA or
  an unrecognized form never silently loses the match.

**Why Workday and iCIMS aren't on the allowlist**, even though they're
extremely common: they're a fundamentally different automation problem,
not just "another form to fill." Workday requires creating a per-tenant
account through a multi-step wizard before you even reach an
application form, and has documented bot detection that blocks naive
automation — the risk there isn't "might fail gracefully," it's "might
get flagged." iCIMS is often multi-step, frequently requires login, and
uses custom JS-driven form rendering that can block standard
programmatic field-filling. Both would need meaningfully more
sophisticated (and riskier) automation than the single-page form-fill
this app does today. Worth revisiting if there's real demand, but not
something to enable by just adding a domain to the list.

**Two name-field conventions, both handled**: Greenhouse/Lever
typically split first/last name into separate fields; Ashby/Workable
commonly use a single combined "Name" field instead. The filler checks
which pattern is actually present (tries first/last first; only falls
back to a combined-name field if those genuinely don't exist) rather
than guessing — verified against local mock forms of both patterns.

**Hosting caveat, worth taking seriously before enabling this in
production:** Playwright needs a real headless Chromium browser, which
needs meaningfully more RAM and disk than Render's free tier typically
provides, plus system-level dependencies (fonts, `libnss`, etc.) that
the standard Python buildpack doesn't include by default. Two things to
check before flipping `AUTO_SUBMIT_ENABLED=true` in production:

1. **Build command** needs an extra step beyond `pip install`:
   ```
   pip install -r requirements.txt && playwright install --with-deps chromium
   ```
   (`--with-deps` attempts to install the OS-level libraries Chromium
   needs — Render's build environment may or may not support this
   cleanly; test it before relying on it.)
2. **Instance size** — the free tier's RAM may not be enough to run a
   real browser alongside the rest of the app. If auto-submit attempts
   start failing or timing out in a way that looks like resource
   exhaustion rather than a real form-filling issue, that's the likely
   cause — worth testing on a paid Render instance before trusting this
   in production.

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

## Job Buddy

Not limited to onboarding-after-a-Riseply-match anymore. A user with an
existing job (found through Riseply or not) can add it directly via
"+ Add a job you already have" on the Job Buddy page — `POST
/applications/current-job` creates a `Job` + `Application` straight at
`status='accepted'`, skipping discovery/matching/approval entirely.

The user selects how long they've been in the role (`tenure_hint` on
the `Application`: `just_started` / `a_few_months` / `well_established`),
which changes what kind of plan gets generated — a genuine content
difference, not just a label:
- `just_started`: first-week checklist + 30/60/90-day plan (the
  original onboarding framing)
- `a_few_months`: where you likely stand + next-90-days goals + common
  stall points at this stage
- `well_established`: where growth typically comes from + next-level
  goals + traps established people fall into

The chat itself is scoped the same way regardless of entry point —
same safety guardrails (redirect legal/medical/harassment/safety
issues to real professionals), broadened from "onboarding topics only"
to ongoing day-to-day work questions for that specific role: a tricky
conversation, asking for more scope or a raise, prioritization, etc.

## Org Buddy as a Service

A separate offering built on the same underlying Job Buddy capability:
lets a company digitize the traditional "assign a buddy to new hires"
practice, grounded in their own real materials instead of generic
advice.

**Trust model, deliberate and non-negotiable**: employee conversation
*content* is never visible to the org admin — only aggregate usage
(`GET /orgs/{id}/usage`: employees joined, plans generated, total/avg
messages). This mirrors how a real human workplace buddy works — they
don't report private conversations back to HR either — and reuses the
same anonymity principle already established by the Rise Index
elsewhere in this app. The response schema for usage stats is
structurally numeric-only; there's no code path that could leak
message content even by accident.

**How it works**: a company admin creates an org (`POST /orgs`), gets a
join code, and uploads custom onboarding material (`POST
/orgs/{id}/content` — handbook excerpts, culture notes, team/tool
info). An employee adding their current job via the existing "current
job" flow can optionally enter that join code; their
`Application.organization_id` gets set, and every plan/chat generated
for them folds in the org's uploaded content alongside their resume
and role info — verified directly that this content actually reaches
the Claude prompt, not just that the plumbing compiles.

No approval flow for org creation — any user can spin one up for their
company, same self-serve pattern as the rest of Riseply. Worth adding
verification (e.g. confirming a work email domain) before this is
opened up to real companies at scale.

**Sidebar visibility**: the "Org Buddy" nav item only shows for users
who actually have admin-level access somewhere — full org admin or
department admin — fetched via `GET /orgs/mine`, which now correctly
includes both roles. A plain employee (joined via a code, no admin
role) or a plain individual user with no org affiliation at all
correctly never sees it, since everything relevant to them is already
surfaced through Job Buddy. This closes a real bug that existed since
department admins were first added: `/orgs/mine` originally only
checked for `role == "admin"`, meaning a department admin got exactly
the same broken "create an organization" prompt a plain employee would
have hit — despite already being a legitimate admin of their own
department. Verified live with all four role types side by side (org
admin, department admin, plain employee, plain individual) that each
sees exactly the sidebar entry appropriate to them, and confirmed the
department admin can now actually reach and use the page correctly,
not just see the link. Caught and fixed a second real bug during that
same verification pass: the Billing card rendered its heading
unconditionally even when the underlying fetch 403'd for a department
admin (billing is legitimately org-wide-admin-only), producing a
visible error toast and an empty card — fixed by catching that fetch
gracefully and hiding the whole card, not just its contents, when it's
out of scope for the viewer.

**Roster upload**: an admin can upload a CSV (`email, title, tenure,
department` columns — all but email optional) via `POST
/orgs/{id}/roster/upload` to pre-register expected hires — exported
from Workday or any HRIS, since this is a plain file upload with no
live API dependency. When someone joins with the org's code and their
email matches a roster entry, their real title/tenure from the roster
is used instead of whatever they typed (verified this directly —
deliberately submitted wrong data in a test and confirmed the roster's
data wins). The roster view shows enrollment status ("joined" / "not
yet joined") per person — this is administrative status, not
conversation content, so it doesn't cross the privacy line above.

**Departments**: real department-level scoping, not just a filter tag.
Each department (`POST /orgs/{id}/departments`) gets its own join
code, distinct from the org-wide one — someone joining with the
org-wide code sees company-wide content only; someone joining with a
department's code sees company-wide content **plus** that
department's own material layered on top. Content and human contacts
can each be scoped company-wide (`department_id: null`) or to a
specific department. A `department_admin` role can manage only their
own department's content/contacts/roster — they cannot touch
company-wide settings or another department's material, verified
directly (a Finance department admin got a clean 403 attempting to
edit both company-wide content and Engineering's content, while
succeeding on Finance's own). If a roster entry has a department
assigned, that takes precedence over whichever code the employee
actually used to join — reflects what the admin knows about someone's
real assignment rather than which specific link they happened to
click. Verified the full layering end-to-end by capturing the actual
prompt sent to Claude for employees in three different situations
(org-wide join, department join, cross-department isolation) rather
than just checking API response shapes.

**Onboarding checklist + manager notification**: admins (or department
admins, for their own department) define checklist items — same
company-wide/department-scoped pattern as content and contacts.
Employees check items off themselves as they go (`POST
/applications/{id}/checklist/{item_id}/complete`), self-directed like
the rest of Job Buddy. The moment every applicable item is complete, a
factual notification goes to the employee's manager if one is on file
(added via the roster CSV's `manager_email` column) — purely
record-keeping, e.g. "Jane completed her onboarding checklist," never
any conversation content. Verified the precise trigger timing
directly: confirmed the notification does NOT fire after a partial
completion, fires exactly once at 100% to the correct manager (checked
the actual email body contains no conversation content), and does NOT
re-fire if an already-completed item gets hit again — a
`manager_notified_at` guard prevents duplicate notifications (e.g. if
an admin adds a new item after someone already finished and they
complete that one too). Also verified the no-manager-on-file case
degrades cleanly — checklist completion still works normally, no crash,
no notification attempted.

**Policy acknowledgment (Code of Ethics, anti-harassment, etc.)**: a
checklist item can carry `policy_content` — when set, this becomes a
distinct type of item. The employee has to actually open and read the
full text (a "Read policy" expand action, not a bare checkbox) before
an explicit "I have read and acknowledge this" action marks it
complete — a real acknowledgment gesture, not an accidental click.

The compliance-critical property, verified directly rather than just
designed: the exact policy text is **snapshotted** into the completion
record at the moment of acknowledgment (`ChecklistCompletion
.policy_content_snapshot`), independent of the live item. Tested this
precisely — had an employee acknowledge version 1 of a policy, then had
the admin edit the live item to version 2, then re-checked the
employee's historical record and confirmed it still read version 1
word-for-word. This is the actual guarantee that matters: if a policy
is later revised, existing employees' acknowledgment records continue
to show precisely what they agreed to at the time, not whatever the
policy currently says — relevant if an acknowledgment is ever
challenged.

Admins get a per-policy acknowledgment record (`GET
/orgs/{id}/checklist/{item_id}/acknowledgments`) — who acknowledged it
and when. Confirmed this is safe within the standing privacy model, not
just asserted: the response schema is structurally limited to
`application_id`, `employee_email`, `employee_name`, `completed_at` —
there's no field it could leak conversation content through even by
accident. This is the same administrative-data category as roster
"joined" status, fundamentally different from Job Buddy chat content,
which never becomes visible to an admin under any circumstance.

**Human handoff**: AI can't give someone an office tour or a
face-to-face introduction — the traditional buddy program's real value
is often precisely those in-person moments. An org admin maintains a
list of real contacts (`POST /orgs/{id}/contacts` — name, email, what
they help with), which feeds into the Job Buddy prompt so it can
naturally mention the right person, and an employee can explicitly
"Request a handoff" — pick a contact, write their own short note, and a
real email goes out. Critically, this carries **only what the employee
themselves wrote**, never their Job Buddy chat history — verified this
directly by planting a deliberately sensitive private message in a
test conversation beforehand and confirming it never appeared in the
resulting email, only the employee's own explicitly-written note did.
This is what keeps the handoff consistent with the privacy model above:
the employee decides exactly what leaves their private conversation,
nothing is auto-summarized or silently forwarded on their behalf.

**Pricing — hybrid (base plan + seat overage)**: Starter ($199/mo, 10
seats) and Growth ($599/mo, 50 seats) are real Stripe subscriptions,
using the exact same Checkout pattern as the individual Pro plan (see
`STRIPE_PRICE_ID_ORG_STARTER` / `_GROWTH` in `.env.example`). **Being
precise about what's automated and what isn't**: the base subscription
charge is fully automated via Stripe, verified through the same
webhook mechanism as individual billing. The *overage* portion (cost
for employees beyond the included seat count) is calculated and shown
clearly on the admin dashboard, but is **not yet automatically
invoiced** — that needs Stripe's metered/usage-based billing, which is
materially more infrastructure than a flat subscription (recurring
usage reporting, a different Price type, webhook handling for usage
records) and wasn't something to build and claim working without a
real Stripe account to verify it against end to end. For now, overage
is visible, not hidden, but reconciling it is a manual step.

**Deliberately not integrating with Workday or other HRIS platforms
directly** — a considered decision, not an unfinished item. Researched
this rather than assumed: Workday requires each customer's own IT
admin to configure a per-tenant Integration System User (there's no
generic OAuth "connect your account" flow Riseply could build once),
software vendors typically need a formal Workday partnership just to
authenticate at all, there are no native webhooks (polling only), and
Workday ships breaking API changes twice a year. CSV roster upload is
the deliberate substitute — it works today for Workday *and* every
other HRIS, since CSV export is universal, without a partnership
agreement or per-customer bespoke integration work that would only pay
off once a specific paying company asks for live sync. If that demand
ever shows up, the practical path is a third-party unified HRIS API
provider (Merge, Unified.to, Knit) rather than a direct Workday
partnership — they abstract Workday *and* BambooHR, ADP, Rippling,
etc. behind one integration effort. Not on the roadmap otherwise.

## Knowledge Base

A grounded Q&A assistant, deliberately conservative: the model is only
ever allowed to answer from real, admin-curated articles retrieved for
the specific question asked — never from general knowledge about how
similar products typically work, since that could be confidently wrong
about Riseply's actual pricing, privacy behavior, or feature details.

**Retrieval** is simple keyword overlap (no embeddings/vector search —
no new infrastructure dependency, good enough for a KB in the
dozens-to-low-hundreds of articles range; worth upgrading to real
semantic search if the article count grows large enough that keyword
matching starts missing relevant content). One real gap this surfaced
during testing: the product's own name ("Riseply") naturally appears in
nearly every article, which made it act as a false-positive match
trigger rather than a useful signal — fixed by excluding it from
retrieval scoring, then re-verified the exact failing case.

**The critical safety property**: when nothing relevant is found, the
model is never called at all (verified directly — mocked the API call
and asserted it was never invoked) rather than being asked to guess.

Auto-seeded on first startup with 10 real starter articles across 6
categories, written with direct knowledge of how each feature actually
works rather than generic placeholder text — an admin can edit or add
to these via the in-app management UI (`GET /kb/*` for
browsing/asking, `POST/PUT/DELETE /kb/articles` admin-only).

## SEO

Public pages (`/`, `/buddy-as-a-service`, `/security`, `/terms`,
`/privacy`, `/login`, `/signup`) were converted from client to server
components where they had no actual interactivity (home, security,
terms, privacy — just static content and links), so each can export
real per-page metadata directly. `/login` and `/signup` genuinely need
`"use client"` for form state, so they keep their page.tsx as a client
component and carry metadata via a sibling `layout.tsx` instead — the
standard pattern for this in Next.js App Router. A real, measurable
side effect: the converted pages' shipped JS dropped from ~1KB+ to
187 bytes each, since they no longer hydrate any client-side React at
all.

**`/buddy-as-a-service`** is the centerpiece — a public marketing page
for Org Buddy that didn't exist before (it previously only lived behind
login in the dashboard, meaning nothing on the public site could ever
rank for or explain that offering to a prospective company). Includes
`Service`/`Offer` structured data for the two paid tiers and `FAQPage`
structured data for the FAQ section, both verified by actually parsing
the JSON-LD out of the built static HTML, not just checking it compiles.

`public/robots.txt` and `public/sitemap.xml` are static files (this app
ships as a static export, so no dynamic sitemap generation) — robots.txt
disallows `/dashboard/*` and the two single-purpose auth transition
pages (forgot/reset password) from being crawled, since none of that is
meant for search discovery.

Root layout adds `metadataBase` (needed for Open Graph URLs to resolve
correctly) and Organization structured data on the homepage.

## Known gaps / next steps

- **No resource library / career content yet** (resume guides, interview
  skill articles, negotiation tips) — flagged as a growth/content lever,
  not yet built.
- **Discovery sources are a fixed list** (`backend/app/services/discovery_sources.py`)
  rather than admin-editable from the UI. Fine for a v1; a future
  improvement would be an admin panel for managing these.
- **Auth is hand-rolled** (JWT + bcrypt) rather than a managed provider.
  This was tested and works correctly, and now has rate limiting +
  optional CAPTCHA against signup abuse (see above) plus a tested
  password reset flow — but for a real public launch with real user
  data, consider migrating to Clerk, Auth.js, or Supabase Auth anyway,
  since they handle things this MVP still doesn't, like email
  verification.
- **No email verification yet** — anyone can sign up with an email they
  don't own; only password reset (which does verify via a real emailed
  link) is built.
