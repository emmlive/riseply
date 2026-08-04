"""
Generic RSS job feed reader. Works with any site that publishes an RSS/Atom
feed of listings (e.g. We Work Remotely category feeds). This is the easiest
way to add a new source without writing a custom scraper.
"""
import feedparser
import hashlib


def fetch_jobs(feed_url: str):
    feed = feedparser.parse(feed_url)
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
