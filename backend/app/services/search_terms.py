"""What a person is looking for, worked out from their search profiles and
their default resume.

Two jobs:

1. resume_job_titles(): read the job titles a resume says the person has
   held. Used to search for jobs when someone has a resume but no search
   profile yet, and as extra signal alongside a profile.
2. title_fits(): a free, no-AI check that a posting's title is anywhere near
   what the person wants. It runs before the paid scoring call, so Claude
   only scores jobs that could plausibly fit, and it enforces the
   "excluded keywords" a profile lists.

Everything here is deterministic and makes no network calls.
"""
import re

# Words that name a kind of job but not which job. "Manager" alone says
# nothing about whether "Sales Manager" fits "IT Audit Manager", so these
# never count as an overlap on their own.
GENERIC_WORDS = frozenset((
    "senior", "sr", "junior", "jr", "lead", "principal", "staff", "associate", "assistant",
    "chief", "head", "vice", "president", "intern", "internship", "trainee", "entry", "level",
    "manager", "director", "engineer", "analyst", "specialist", "consultant", "coordinator",
    "officer", "administrator", "executive", "representative", "agent", "developer", "architect",
    "supervisor", "technician", "advisor", "adviser", "partner", "owner", "professional",
    "remote", "hybrid", "onsite", "contract", "fulltime", "parttime", "time", "full", "part",
    "and", "the", "for", "of", "with", "in", "at", "to", "a", "an", "or", "ii", "iii", "iv",
    "team", "group", "global", "company", "corporate",
))

# A line in a resume counts as a job title only if it names a kind of job.
ROLE_NOUNS = (
    "engineer", "analyst", "manager", "director", "specialist", "auditor", "consultant",
    "developer", "designer", "architect", "administrator", "coordinator", "officer", "scientist",
    "accountant", "nurse", "technician", "supervisor", "executive", "lead", "planner",
    "scheduler", "recruiter", "teacher", "instructor", "attorney", "paralegal", "controller",
    "strategist", "producer", "writer", "editor", "representative", "associate", "advisor",
    "researcher", "pharmacist", "therapist", "estimator", "inspector", "buyer", "operator",
)

_DATE_WORDS = re.compile(
    r"\b(19|20)\d{2}\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b|\bpresent\b|\bcurrent\b",
    re.I,
)
_SECTION_HEADS = re.compile(
    r"^(experience|work experience|professional experience|employment|summary|profile|skills|education|"
    r"certifications?|projects?|objective|contact|references|awards|publications)\b", re.I)


def _stem(word: str) -> str:
    """Crude on purpose, and short on purpose: 'nurse', 'nurses' and 'nursing'
    all meet at 'nurs', 'auditor' and 'audit' at 'audi'. Words over 4 letters
    are cut to 4. This check only ever lets a job THROUGH, so matching too
    loosely costs one cheap scoring call, while matching too tightly hides a
    job the person wanted."""
    word = word.lower()
    return word[:4] if len(word) > 4 else word


# Different words for the same kind of work. A profile that says
# "Cybersecurity Architect" must still see "Security Architect".
_FAMILIES = (
    {"cybe", "secu"},
    {"nurs", "rn", "regi"},
    {"audi", "assu"},
    {"soft", "prog", "deve", "code"},
    {"data", "anal"},
    {"plan", "sche", "prim"},
    {"clou", "devo", "infr"},
)


# Technical job names that are used for one another all the time.
_TECH_ROLES = {"engineer", "developer", "programmer", "architect"}


def _has_tech_role(text: str) -> bool:
    return bool(set(re.split(r"[^a-z]+", (text or "").lower())) & _TECH_ROLES)


def _expand(stems: set[str]) -> set[str]:
    out = set(stems)
    for family in _FAMILIES:
        if stems & family:
            out |= family
    return out


# Two-letter words that carry no meaning in a job title. Real abbreviations
# (IT, RN, HR, QA, UX) are kept for title matching.
_SHORT_NOISE = frozenset(("of", "in", "at", "to", "or", "an", "is", "as", "on", "by", "be", "us", "uk", "co", "if", "no", "so", "we", "up", "ii"))


def _distinctive_stems(text: str, titles: bool = True) -> set[str]:
    """Two-letter abbreviations count in titles ("RN", "IT") but not in running
    description text, where "it" is just the word."""
    words = re.split(r"[^a-z0-9+#]+", (text or "").lower())
    floor = 2 if titles else 3
    return {_stem(w) for w in words if len(w) >= floor and w not in GENERIC_WORDS and w not in _SHORT_NOISE}


def resume_job_titles(resume_text: str, limit: int = 4) -> list[str]:
    """The job titles a resume lists, most recent first (resumes put the
    newest job first). Looks for short lines that name a kind of job, with
    dates and "at Company" tails stripped. Returns [] when it can't tell,
    which callers treat as "no signal", never as an error."""
    titles: list[str] = []
    seen: set[str] = set()
    for raw in (resume_text or "").splitlines()[:150]:
        line = raw.strip(" \t-•*|:,;")
        if not line or len(line) > 90 or _SECTION_HEADS.match(line):
            continue
        # "Senior IT Auditor, Acme Corp 2019 - Present" -> "Senior IT Auditor"
        line = _DATE_WORDS.split(line)[0] if _DATE_WORDS.search(line) else line
        line = re.split(r"\s+(?:at|@|-|–|—|\|)\s+|,\s+|\s{3,}", line)[0].strip(" \t-•*|:,;()")
        words = line.split()
        if not 1 < len(words) <= 6:
            continue
        lowered = [w.lower().strip(".,()") for w in words]
        if not any(w in ROLE_NOUNS for w in lowered):
            continue
        # Sentences and bullets about duties are not titles.
        if any(w in ("responsible", "managed", "led", "developed", "built", "worked", "i", "my", "we")
               for w in lowered):
            continue
        key = " ".join(lowered)
        if key in seen:
            continue
        seen.add(key)
        titles.append(" ".join(w for w in words))
        if len(titles) >= limit:
            break
    return titles


def implicit_profile(resume_text: str, location: str = "") -> dict | None:
    """The search someone gets when they have a default resume but no search
    profile: their own past titles, anywhere, a fair bar. None if the resume
    names no recognizable job."""
    titles = resume_job_titles(resume_text)
    if not titles:
        return None
    return {
        "name": "From your resume",
        "titles": titles,
        "locations": [],
        "seniority": [],
        "min_match_score": 70,
        "exclude_companies": [],
        "keywords_required": [],
        "keywords_excluded": [],
        "active": True,
        # Not a hard filter (a hard city match would hide nearby towns); the
        # scorer reads it as context.
        "home_location": (location or "").strip(),
    }


def title_fits(job_title: str, profiles: list[dict], description: str = "") -> bool:
    """False only when no active profile could plausibly want this job.

    A profile accepts a job when the title, or the start of the description,
    shares a distinctive word (or a word for the same kind of work) with one
    of the profile's titles or required keywords, and the title contains none
    of the profile's excluded keywords. A profile with no titles or keywords
    to compare against accepts everything, so an unusual search is never
    starved by this check. Err toward letting jobs through: the scorer makes
    the real decision."""
    job_title = job_title or ""
    title_stems = _expand(_distinctive_stems(job_title))
    desc_stems = _expand(_distinctive_stems(description, titles=False)) if description else set()
    lowered = job_title.lower()
    for profile in profiles:
        if not profile.get("active", True):
            continue
        excluded = [k.strip().lower() for k in profile.get("keywords_excluded", []) if k and k.strip()]
        if any(re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", lowered) for k in excluded):
            continue
        wanted: set[str] = set()
        for term in list(profile.get("titles", [])) + list(profile.get("keywords_required", [])):
            wanted |= _distinctive_stems(term)
        if not wanted:
            return True
        wanted = _expand(wanted)
        if (title_stems | desc_stems) & wanted:
            return True
        # "Software Engineer" should still see "Backend Developer".
        if _has_tech_role(job_title) and any(_has_tech_role(t) for t in profile.get("titles", [])):
            return True
    return False
