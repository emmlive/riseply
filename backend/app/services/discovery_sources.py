"""
Where discovery pulls job postings from. These are shared across all users
(the postings themselves aren't tenant-specific — only the matching and
applications are). For an MVP this is a fixed list; a future improvement
could let admins manage this from a UI instead of editing code.
"""

RSS_JOB_FEEDS = [
    "https://remotive.com/remote-jobs/feed",  # all categories; matcher filters relevance per user
    # WWR's single all-jobs feed, not individual category feeds -- covers
    # every category they publish (Programming, DevOps/Sysadmin, Design,
    # Product, Customer Support, Sales & Marketing, Management &
    # Finance, and "All Other") in one official feed. Picking specific
    # categories by hand is the same curation-bias problem as a
    # hardcoded company list, just one level removed -- this avoids
    # that entirely rather than trying to guess which categories matter.
    # Confirmed via https://weworkremotely.com/remote-job-rss-feed.
    "https://weworkremotely.com/remote-jobs.rss",
]

GREENHOUSE_COMPANIES: list[str] = [
    "anthropic",          # AI safety
    "scaleai",            # AI/ML infrastructure
    "hiddenlayer",        # AI/ML security is their entire business
    "andurilindustries",  # defense tech, AI governance/compliance-adjacent roles
]

LEVER_COMPANIES: list[str] = [
    "crypto",  # Crypto.com -- has posted AI Security Engineer roles directly
]
