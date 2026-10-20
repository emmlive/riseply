"""Short videos for what the Career Coach is teaching.

Finds real, embeddable YouTube videos by searching: the model never names
videos, so there is nothing to make up. With no API key set it returns only a
link that opens the YouTube search, which needs no setup. Results are cached
for a month because a YouTube search is a large share of the free daily quota
and the same topics come up again and again.

Safe search is on and only embeddable videos are returned. Titles and channel
names are shown as plain text. Video ids are checked against YouTube's id
format before they reach the page.
"""
import json
import re
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import httpx
from sqlalchemy.orm import Session

from app import models
from app.config import settings

API_URL = "https://www.googleapis.com/youtube/v3/search"
CACHE_DAYS = 30
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def normalize(q: str) -> str:
    q = re.sub(r"\s+", " ", str(q or "")).strip()[:100]
    return q


def search_phrase(q: str) -> str:
    q = normalize(q)
    return q if re.search(r"\b(tutorial|explained|how to|walkthrough)\b", q, re.I) else f"{q} tutorial"


def search_url(q: str) -> str:
    return "https://www.youtube.com/results?search_query=" + quote_plus(search_phrase(q))


def enabled() -> bool:
    return bool(settings.youtube_api_key)


def parse(payload: dict) -> list[dict]:
    out = []
    for item in (payload.get("items") or []):
        vid = ((item.get("id") or {}).get("videoId") or "")
        sn = item.get("snippet") or {}
        if not _ID_RE.match(vid):
            continue
        thumbs = sn.get("thumbnails") or {}
        thumb = (thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
        out.append({
            "id": vid,
            "title": re.sub(r"\s+", " ", str(sn.get("title") or "")).strip()[:120],
            "channel": re.sub(r"\s+", " ", str(sn.get("channelTitle") or "")).strip()[:60],
            "thumb": thumb if thumb.startswith("https://") else "",
        })
    return out[:4]


def fetch(q: str) -> list[dict]:
    """One YouTube search. Raises on any failure."""
    r = httpx.get(API_URL, timeout=8.0, params={
        "part": "snippet", "type": "video", "maxResults": 6, "q": search_phrase(q),
        "videoEmbeddable": "true", "safeSearch": "strict", "relevanceLanguage": "en",
        "key": settings.youtube_api_key,
    })
    r.raise_for_status()
    return parse(r.json())


def cached(db: Session, q: str) -> list[dict] | None:
    key = search_phrase(q).lower()
    row = db.query(models.VideoSearchCache).filter_by(query_key=key).first()
    if not row or row.created_at < datetime.utcnow() - timedelta(days=CACHE_DAYS):
        return None
    try:
        return json.loads(row.data)
    except Exception:
        return None


def save(db: Session, q: str, videos: list[dict]) -> None:
    key = search_phrase(q).lower()
    row = db.query(models.VideoSearchCache).filter_by(query_key=key).first()
    if row:
        row.data, row.created_at = json.dumps(videos), datetime.utcnow()
    else:
        db.add(models.VideoSearchCache(query_key=key, data=json.dumps(videos)))
    db.commit()
