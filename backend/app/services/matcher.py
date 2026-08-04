import json
import os
from anthropic import Anthropic

from app.config import settings

client = Anthropic(api_key=settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", ""))
MODEL = "claude-sonnet-4-6"


def score_job(resume_text: str, job: dict, profile: dict) -> dict:
    prompt = f"""You are helping a job seeker filter job postings. Score how
well this job matches their resume and stated criteria.

RESUME:
{resume_text}

SEARCH CRITERIA:
{json.dumps(profile, indent=2)}

JOB POSTING:
Title: {job['title']}
Company: {job['company']}
Location: {job['location']}
Description:
{job['description'][:6000]}

Respond ONLY with JSON, no other text, in this exact shape:
{{"score": <0-100 integer>, "reason": "<one sentence>"}}
"""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"score": 0, "reason": "Could not parse model response"}


def best_profile_match(job: dict, resume_text: str, profiles: list[dict]) -> dict:
    """Scores one job against every active search profile, returns the best:
    {"profile_name": str, "score": int, "reason": str, "meets_threshold": bool}
    """
    best = None
    for profile in profiles:
        if not profile.get("active", True):
            continue
        if job["company"].lower() in {c.lower() for c in profile.get("exclude_companies", [])}:
            continue
        result = score_job(resume_text, job, profile)
        candidate = {
            "profile_name": profile["name"],
            "score": result["score"],
            "reason": result["reason"],
            "meets_threshold": result["score"] >= profile.get("min_match_score", 70),
        }
        if best is None or candidate["score"] > best["score"]:
            best = candidate

    return best or {"profile_name": None, "score": 0, "reason": "no active profiles",
                     "meets_threshold": False}
