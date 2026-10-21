"""A free first look at whether a posting is the kind of work the resume shows.

Before paying for an AI score, check how many of the posting's own key terms
(tools, skills, certifications, domain words) appear anywhere in the resume.
A posting that shares almost none of them is a different field, whatever its
title says. Deterministic, no network.
"""
from app.services import job_terms

MIN_TERMS = 6      # fewer key terms than this and the posting is too thin to judge
MIN_SHARE = 0.12   # at least this share of its key terms must appear in the resume


def check(resume_text: str, description: str) -> dict:
    """{"fits": bool|None, "share": float, "terms": n}. fits is None when we can't tell."""
    if not (resume_text or "").strip():
        return {"fits": None, "share": 0.0, "terms": 0}
    terms = job_terms.key_terms(description or "", limit=18)
    if len(terms) < MIN_TERMS:
        return {"fits": None, "share": 0.0, "terms": len(terms)}
    hits = sum(1 for t in terms if job_terms.has_term(resume_text, t))
    share = hits / len(terms)
    return {"fits": share >= MIN_SHARE, "share": round(share, 2), "terms": len(terms)}
