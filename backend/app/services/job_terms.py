"""What an applicant tracking system looks for, checked without AI.

Most screening software (and many recruiters) search for the posting's own
words and filter on a few hard requirements (years of experience, a degree, a
certification, a clearance). This module pulls the key terms and those hard
requirements out of a job posting and checks them against a resume, so the
person can see exactly what a screen would find and what it would miss. It is
deterministic, so it costs nothing and gives the same answer every time.
"""
import re

_STOP = frozenset("""
a about above across after all also am an and any are as at be been being both but by can could did do does doing each
either every for from had has have having how i if in into is it its just may me more most must my no nor not of off on
once only or other our out over own per same shall she should so some such than that the their them then there these
they this those through to too under until up us very was we were what when where which while who whom why will with
within without would you your yours able ability abilities across additional apply applicant applicants applying
benefits business candidate candidates career careers company companies day days description duties employer
employment environment equal etc experience experienced familiarity good great help helping including include includes
job join knowledge level looking make meet need needed needs new office one opportunity opportunities organization
part people plus position preferred prior provide provides qualifications qualified related relevant required
requirement requirements responsibilities responsibility responsible role roles salary seeking skill skills strong
support team teams time top understanding use using various want well work working works year years you'll we're
youll weve seek seeking ideal excellent proven demonstrated overview summary location full part-time full-time remote
hybrid onsite on-site paid pay range compensation bonus insurance medical dental vision vacation holiday holidays
""".split())

_REQ_HEAD = re.compile(
    r"(requirements?|qualifications?|what you['’]ll need|what we['’]re looking for|must[- ]haves?|you have|you bring|about you)",
    re.I)
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#./&-]*")
_CERTS = ("CISA", "CISSP", "CISM", "CRISC", "CEH", "OSCP", "CPA", "CMA", "CFA", "PMP", "PRINCE2", "CAPM", "CSM", "CCNA", "CCNP",
          "Security+", "Network+", "AWS Certified", "Azure", "SHRM", "PHR", "SPHR", "RN", "CPR", "ITIL", "Six Sigma", "CompTIA")
_DEGREE = re.compile(r"\b(bachelor|master|mba|ph\.?d|doctorate|associate|b\.?s\.?|b\.?a\.?|m\.?s\.?|degree)\b", re.I)
_CLEARANCE = re.compile(r"\b(security clearance|top secret|ts/sci|secret clearance|public trust|clearance)\b", re.I)


def _clean_token(t: str) -> str:
    t = t.strip(".-/&")
    return t


_NOISE = frozenset("bachelor bachelors master masters degree degrees information systems".split())


def _tokens(text: str) -> list[tuple[str, bool]]:
    """(token, looks_like_a_name_or_acronym) for every word, in order."""
    out = []
    for m in _TOKEN.finditer(text or ""):
        t = _clean_token(m.group())
        if not t:
            continue
        before = (text[:m.start()].rstrip(" \t") or "\n")[-1]
        mid_sentence = before not in ".:;!?-•*·–—(\n"
        special = (t.isupper() and 2 <= len(t) <= 8) or bool(re.search(r"[+#]|\.[a-z]|[A-Za-z]/[A-Za-z]", t)) \
                  or (t[0].isupper() and t[1:].islower() and mid_sentence and len(t) >= 5)
        out.append((t, special))
    return out


def key_terms(description: str, limit: int = 18) -> list[str]:
    """The words and short phrases the posting leans on, most important first."""
    text = description or ""
    head = _REQ_HEAD.search(text)
    req_text = text[head.start():] if head else ""

    toks = _tokens(text)
    req_counts: dict[str, int] = {}
    for t, _ in _tokens(req_text):
        req_counts[t.lower()] = req_counts.get(t.lower(), 0) + 1

    counts: dict[str, int] = {}
    shown: dict[str, str] = {}
    special: set[str] = set()
    for t, sp in toks:
        k = t.lower()
        acronym = t.isupper() and 2 <= len(t) <= 8 and k not in ("and", "the", "for", "our", "you", "all")
        if (k in _STOP and not acronym) or k in _NOISE or (len(k) < 3 and not sp):
            continue
        counts[k] = counts.get(k, 0) + 1
        shown.setdefault(k, t if sp or t.isupper() else k)
        if sp:
            special.add(k)

    # Two-word phrases made of two meaningful words ("risk management").
    pair_counts: dict[str, int] = {}
    prev = None
    for t, sp in toks:
        k = t.lower()
        if k in _STOP or len(k) < 3:
            prev = None
            continue
        if prev:
            pair_counts[f"{prev} {k}"] = pair_counts.get(f"{prev} {k}", 0) + 1
        prev = k

    scored: list[tuple[float, str]] = []
    for k, c in counts.items():
        if c < 2 and k not in special:
            continue
        s = c + (3 if k in special else 0) + 1.5 * req_counts.get(k, 0)
        scored.append((s, shown[k]))
    pairs = []
    for p, c in pair_counts.items():
        if c >= 2:
            a, b = p.split()
            pairs.append((c + 2 + 1.5 * min(req_counts.get(a, 0), req_counts.get(b, 0)), p))

    chosen_pairs = [p for _, p in sorted(pairs, reverse=True)[:6]]
    covered = {w for p in chosen_pairs for w in p.split()}
    out: list[str] = list(chosen_pairs)
    for _, term in sorted(scored, reverse=True):
        if term.lower() in covered and counts.get(term.lower(), 0) <= 3:
            continue
        out.append(term)
        if len(out) >= limit:
            break
    seen, final = set(), []
    for t in out:
        if t.lower() not in seen:
            seen.add(t.lower())
            final.append(t)
    return final[:limit]


def has_term(resume_text: str, term: str) -> bool:
    t = term.lower()
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]   # "audits" in the posting matches "audit" on the resume, and the reverse
    pat = r"(?<![A-Za-z0-9])" + re.escape(t).replace(r"\ ", r"[\s-]+") + r"(?:s|es)?(?![A-Za-z0-9])"
    return re.search(pat, (resume_text or "").lower()) is not None


def coverage(description: str, original: str, tailored: str) -> dict:
    terms = key_terms(description)
    rows = [{"term": t, "in_original": has_term(original, t), "in_tailored": has_term(tailored, t)} for t in terms]
    return {"terms": rows, "total": len(rows),
            "found": sum(1 for r in rows if r["in_tailored"]),
            "found_before": sum(1 for r in rows if r["in_original"])}


# ---- hard requirements a screen may filter on ------------------------------
_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|to)?\s*(?:\d{1,2})?\s*\+?\s*years?[^.\n]{0,40}?experience|experience[^.\n]{0,40}?(\d{1,2})\s*\+?\s*years?", re.I)
_RANGE = re.compile(
    r"(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+)?((?:19|20)\d{2})\s*(?:-|–|—|to)\s*"
    r"(?:(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+)?((?:19|20)\d{2})|(present|current|now))", re.I)


def years_asked(description: str) -> int | None:
    found = []
    for m in _YEARS.finditer(description or ""):
        n = m.group(1) or m.group(2)
        if n and 0 < int(n) <= 30:
            found.append(int(n))
    return min(found) if found else None   # the lowest figure is the usual minimum


def years_shown(resume_text: str, this_year: int) -> int:
    """Years covered by the dated ranges on the resume (overlaps counted once)."""
    spans = []
    for m in _RANGE.finditer(resume_text or ""):
        start = int(m.group(1))
        end = this_year if m.group(3) else int(m.group(2))
        if 1970 <= start <= end <= this_year + 1:
            spans.append((start, end))
    spans.sort()
    total, cur_s, cur_e = 0, None, None
    for s, e in spans:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total


def screening_checks(description: str, resume_text: str, this_year: int) -> list[dict]:
    """Hard requirements named in the posting, each with whether the resume shows it.
    [{label, ok, detail}]. A failed check is a prompt to look, not a verdict."""
    out = []
    asked = years_asked(description)
    if asked:
        shown = years_shown(resume_text, this_year)
        ok = shown >= asked
        out.append({"label": f"{asked}+ years of experience", "ok": ok,
                    "detail": (f"Your dated roles add up to about {shown} years." if ok else
                               f"The posting asks for {asked}+ years; your dated roles add up to about {shown}. "
                               "If you have more, make sure every role has dates.")})
    if _DEGREE.search(description or ""):
        ok = bool(_DEGREE.search(resume_text or ""))
        out.append({"label": "Degree", "ok": ok,
                    "detail": "Your education is on the resume." if ok else
                    "The posting mentions a degree and your resume doesn't show one. Add your Education section if you have it."})
    for cert in _CERTS:
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(cert) + r"(?![A-Za-z0-9])", description or ""):
            ok = has_term(resume_text, cert)
            out.append({"label": f"{cert}", "ok": ok,
                        "detail": f"{cert} is on your resume." if ok else
                        f"The posting names {cert}. Add it only if you hold it (or are in progress, and say so)."})
    if _CLEARANCE.search(description or ""):
        ok = bool(_CLEARANCE.search(resume_text or ""))
        out.append({"label": "Security clearance", "ok": ok,
                    "detail": "Your clearance is on the resume." if ok else
                    "The posting mentions a clearance. If you hold one, say the level on your resume."})
    return out[:8]
