"""
Where discovery pulls job postings from. These are shared across all users
(the postings themselves aren't tenant-specific — only the matching and
applications are). For an MVP this is a fixed list; a future improvement
could let admins manage this from a UI instead of editing code.
"""

RSS_JOB_FEEDS = [
    "https://remotive.com/remote-jobs/feed",  # all categories; matcher filters relevance per user
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    # GRC Careers -- a job board purpose-built for governance, risk,
    # compliance, audit, and AI-governance roles. Confirmed live (real
    # RSS content-type, current postings from real companies) as of
    # this writing. Explicitly published for syndication (their own
    # footer links to /feed.xml under "Syndicate"), same category as
    # the WWR feeds above -- not scraping. Directly complements the
    # engineering-skewed GREENHOUSE_COMPANIES/LEVER_COMPANIES lists
    # below, which have essentially nothing for this industry.
    "https://www.ai-governance-jobs.com/feed.xml",
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
