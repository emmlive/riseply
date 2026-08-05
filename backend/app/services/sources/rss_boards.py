"""
Generic RSS job feed reader. Works with any site that publishes an RSS/Atom
feed of listings (e.g. We Work Remotely category feeds). This is the easiest
way to add a new source without writing a custom scraper.
"""
import feedparser
import hashlib
import requests

# Some feed hosts block requests with no User-Agent (or one that
# self-identifies as a bot/scraper) as basic bot mitigation. A realistic
# browser-style UA avoids that without doing anything deceptive -- this
# is a real person's job search pulling a public RSS feed, not scraping
# anything private. Note: this alone doesn't guarantee access -- some
# hosts block by IP range (e.g. known cloud/datacenter ASNs) regardless
# of what UA is sent, which is a separate problem this can't fix.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_jobs(feed_url: str):
    # feedparser.parse() given a bare URL has NO timeout at all -- if the
    # feed server is slow or hangs, this blocks far longer than any
    # browser or proxy will wait, and the whole request eventually dies
    # in a way that looks like a CORS failure to the client (no response
    # ever completes, so there's nothing to check CORS headers against).
    # Fetching with `requests` first gives us the same timeout control
    # used everywhere else in this codebase, then handing feedparser the
    # already-downloaded bytes to parse (it accepts bytes/str directly,
    # not just a URL).
    resp = requests.get(feed_url, timeout=15, headers=HEADERS)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)

    jobs = []
    for entry in feed.entries:
        external_id = hashlib.sha1(entry.get("link", "").encode()).hexdigest()[:16]
        jobs.append({
            "source": f"rss:{feed.feed.get('title', feed_url)}",
            "external_id": external_id,
            "company": entry.get("author", ""),
            "title": entry.get("title", ""),
            "location": "",  # rarely structured in RSS; matcher can infer from description
            "url": entry.get("link", ""),
            "description": entry.get("summary", ""),
        })
    return jobs


def fetch_all(feed_urls: list[str]):
    all_jobs = []
    for url in feed_urls:
        try:
            all_jobs.extend(fetch_jobs(url))
        except Exception as e:
            print(f"[rss] failed for {url}: {e}")
    return all_jobs
