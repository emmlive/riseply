"""
Seeds a starting set of real, accurate KB articles on first startup --
idempotent (only runs if the table is empty), same spirit as the
self-healing schema migration. Written with genuine knowledge of how
each feature actually works, not generic placeholder text -- an admin
can edit or add to these later via the KB admin UI.
"""
from sqlalchemy.orm import Session
from app import models

SEED_ARTICLES = [
    {
        "category": "Billing",
        "title": "What's the difference between Free and Pro?",
        "content": (
            "Free gives you 50 job matches, 15 tailored resumes, 10 interview preps, "
            "5 onboarding plans, and 60 Job Buddy messages per month, capped at 1 "
            "active search profile. Pro (roughly 5x the limits: 300 matches, 100 "
            "tailored resumes, 50 interview preps, 30 onboarding plans, 500 Job Buddy "
            "messages) also unlocks up to 10 simultaneous search profiles. Check the "
            "Billing tab for your account's exact current usage against these limits."
        ),
    },
    {
        "category": "Billing",
        "title": "How do I upgrade, downgrade, or cancel?",
        "content": (
            "Go to the Billing tab. If you're on Free, there's an 'Upgrade to Pro' "
            "button that takes you to a secure Stripe checkout. If you're already on "
            "Pro, you'll see a 'Manage subscription' button instead, which opens "
            "Stripe's own billing portal -- you can update your card, view invoices, "
            "or cancel from there. Cancelling takes effect at the end of your current "
            "billing period; you keep Pro access until then."
        ),
    },
    {
        "category": "Matching",
        "title": "How does job matching work?",
        "content": (
            "When you click 'Find new matches,' Riseply pulls fresh postings from its "
            "job sources, then scores each one against your resume and every active "
            "search profile you have, using Claude. A posting only gets queued for "
            "your review if it clears that profile's minimum match score (60% by "
            "default for new profiles -- you can adjust this per profile). If nothing "
            "clears your bar, you'll see the closest few near-misses instead of a "
            "blank result, so you can see the tool is actually working and adjust "
            "your criteria if needed."
        ),
    },
    {
        "category": "Matching",
        "title": "Will Riseply submit applications for me automatically?",
        "content": (
            "Not by default. You review and approve every match yourself, and "
            "normally you apply on the company's site and then click 'Mark as "
            "applied' to track it. There is an optional auto-submit feature, off by "
            "default, that can fill and submit forms automatically -- but only for "
            "already-approved matches, and only on Greenhouse, Lever, Ashby, or "
            "Workable job postings specifically. LinkedIn and Indeed are explicitly "
            "blocked and cannot be auto-submitted to under any setting."
        ),
    },
    {
        "category": "Job Buddy",
        "title": "What is Job Buddy?",
        "content": (
            "Job Buddy is an ongoing work mentor -- available once an application "
            "reaches 'Accepted,' whether that happened through Riseply's own matching "
            "or because you added a job you already have. It generates a plan (a "
            "first-week/30-60-90-day plan if you're just starting, or a growth-focused "
            "plan if you're already established in the role) and gives you an "
            "ongoing chat for day-to-day work questions -- not just onboarding, but "
            "asking for more scope, navigating a tricky conversation, prioritizing "
            "your work, and similar."
        ),
    },
    {
        "category": "Job Buddy",
        "title": "Can my employer see what I say to Job Buddy?",
        "content": (
            "No, not the content of your conversation. If your company has set up "
            "'Org Buddy as a Service,' their admin can only see aggregate usage "
            "(how many employees have joined, how many plans were generated, "
            "average message counts) -- never what anyone actually said. The one "
            "exception: if you explicitly use the 'Request a handoff' feature to "
            "connect with a real person at your company (for something like an "
            "office tour), only the note you personally write gets sent to that "
            "person -- your chat history is never included or summarized."
        ),
    },
    {
        "category": "Org Buddy",
        "title": "What is Org Buddy as a Service?",
        "content": (
            "A company-customized version of Job Buddy, meant to digitize the "
            "traditional practice of assigning new hires a workplace buddy. A "
            "company admin creates an organization, gets a join code to share with "
            "new hires, and can upload real company material (handbook excerpts, "
            "culture notes, team/tool info) that gets folded into every plan and "
            "chat reply for their employees, so advice is grounded in the real "
            "company instead of generic assumptions. Admins can also upload a CSV "
            "roster to pre-register expected hires' titles, and add real human "
            "contacts employees can request a handoff to."
        ),
    },
    {
        "category": "Rise Index",
        "title": "What is the Rise Index?",
        "content": (
            "Live, anonymized response-rate data pulled from everyone using "
            "Riseply -- for example, '68% of applicants heard back from Acme Corp "
            "within 9 days.' A company's stats only become visible once enough "
            "people have applied there (a minimum sample size), specifically to "
            "keep individual applicants unidentifiable. You also earn Rise Points "
            "and build a daily streak for effort -- searching, reviewing matches, "
            "applying, prepping -- never for outcomes like landing an interview, "
            "since outcomes aren't something you fully control."
        ),
    },
    {
        "category": "Account",
        "title": "I forgot my password -- how do I reset it?",
        "content": (
            "On the login page, click 'Forgot password?' and enter your email. "
            "If an account exists for that address, you'll get a reset link by "
            "email (valid for 30 minutes, usable once). Resetting your password "
            "also logs you out of any other active sessions automatically, as a "
            "safety measure."
        ),
    },
    {
        "category": "Account",
        "title": "How do I delete my account or change my login email?",
        "content": (
            "Reach out via the Support tab and a person will take care of it -- "
            "these aren't currently self-service actions in the app."
        ),
    },
]


def seed_kb_if_empty(db: Session):
    if db.query(models.KnowledgeBaseArticle).count() > 0:
        return
    for a in SEED_ARTICLES:
        db.add(models.KnowledgeBaseArticle(category=a["category"], title=a["title"], content=a["content"]))
    db.commit()
