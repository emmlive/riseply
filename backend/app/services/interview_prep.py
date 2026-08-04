import os
from anthropic import Anthropic

from app.config import settings

client = Anthropic(api_key=settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", ""))
MODEL = "claude-sonnet-4-6"


def generate_prep_brief(resume_text: str, job: dict) -> str:
    prompt = f"""Create an interview prep brief for this candidate and job.

RESUME:
{resume_text}

JOB:
Title: {job['title']}
Company: {job['company']}
Description:
{job['description'][:6000]}

Include, with clear headers:
1. Likely interview questions (technical + behavioral) specific to this
   role, with a short bullet on how the candidate could approach each
   based on their real background.
2. Talking points connecting the candidate's actual experience to what
   this job needs.
3. 4-5 smart questions the candidate could ask the interviewer.

Keep it concise and practical, not generic advice. Plain text, use simple
line-based headers (e.g. "LIKELY QUESTIONS"), no markdown formatting.
"""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()
