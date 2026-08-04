import os
from anthropic import Anthropic

from app.config import settings

client = Anthropic(api_key=settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", ""))
MODEL = "claude-sonnet-4-6"


def generate_onboarding_plan(resume_text: str, job: dict) -> str:
    prompt = f"""This candidate just accepted a job offer. Create a practical
onboarding plan to help them ramp up well.

CANDIDATE BACKGROUND:
{resume_text}

NEW ROLE:
Title: {job['title']}
Company: {job['company']}
Description:
{job['description'][:6000]}

Include, with clear plain-text headers (no markdown):
1. FIRST WEEK CHECKLIST — concrete things to do/set up/learn in the first
   few days.
2. 30/60/90-DAY PLAN — realistic goals for each phase, grounded in what
   this specific role likely involves.
3. QUESTIONS FOR YOUR MANAGER — smart questions to ask in early 1:1s to
   clarify expectations and priorities.
4. WATCH-OUTS — a few honest, specific things new hires in similar roles
   often stumble on early, and how to avoid them.

Keep it concrete and specific to this role, not generic career advice.
"""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1800,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def chat_reply(resume_text: str, job: dict, plan: str, history: list[dict], new_message: str) -> str:
    """history is a list of {"role": "user"|"assistant", "content": str},
    oldest first. Returns the mentor's reply text."""
    system_prompt = f"""You are this person's onboarding mentor — a "job
buddy" for their first weeks at a new role. Be direct, practical, and
warm, the way a genuinely good mentor at the company would be: honest
about trade-offs, specific rather than generic, and not afraid to say
"it depends" and then help them think it through.

You know their background and the onboarding plan already made for them.
Use that context naturally; don't repeat it back at them unless it's
relevant to their question.

CANDIDATE BACKGROUND:
{resume_text}

ROLE:
{job['title']} at {job['company']}
{job['description'][:4000]}

ONBOARDING PLAN ALREADY GIVEN TO THEM:
{plan[:3000]}
"""
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": new_message})

    resp = client.messages.create(
        model=MODEL,
        max_tokens=800,
        system=system_prompt,
        messages=messages,
    )
    return resp.content[0].text.strip()
