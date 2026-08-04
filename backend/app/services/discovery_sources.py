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
]

GREENHOUSE_COMPANIES: list[str] = [
    # "stripe", "figma", ...
]

LEVER_COMPANIES: list[str] = [
    # "netflix", ...
]
