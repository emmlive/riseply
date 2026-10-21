"""One ATS readiness number from checks that already exist.

Combines three things a screen looks at, each worked out without AI:
  format       the layout and structure checks (contact, section names, dates, plain layout, length)
  keywords     how many of the posting's key words are on the resume
  requirements the hard filters named in the posting (years, degree, certifications, clearance)

It is an estimate of readiness for keyword and filter screening, not a prediction
of any particular employer's system, and the page says so. Requirements only count
when the posting names some; otherwise their weight goes to the other two.
"""

WEIGHTS = {"format": 30, "keywords": 50, "requirements": 20}


def _share(items) -> float | None:
    items = list(items)
    return (sum(1 for x in items if x) / len(items)) if items else None


def label_for(score: int) -> str:
    return "Strong" if score >= 80 else "Fair" if score >= 60 else "Needs work"


def compute(format_checks: list[dict], cov: dict, req_checks: list[dict]) -> dict:
    fmt = _share(c["ok"] for c in format_checks)
    kw = (cov["found"] / cov["total"]) if cov.get("total") else None
    req = _share(c["ok"] for c in req_checks)

    parts = {"format": fmt, "keywords": kw, "requirements": req}
    live = {k: v for k, v in parts.items() if v is not None}
    total_w = sum(WEIGHTS[k] for k in live) or 1
    score = round(100 * sum(WEIGHTS[k] * v for k, v in live.items()) / total_w)

    # The single most useful next step: the part losing the most points.
    loss = {k: WEIGHTS[k] * (1 - v) / total_w for k, v in live.items()}
    worst = max(loss, key=loss.get) if loss else None
    missing_kw = (cov.get("total") or 0) - (cov.get("found") or 0)
    if not worst or loss[worst] < 0.02:
        nxt = "Nothing urgent. Read it once for sense, then apply."
    elif worst == "keywords":
        nxt = (f"{missing_kw} key word{'s' if missing_kw != 1 else ''} from the posting "
               f"{'are' if missing_kw != 1 else 'is'} missing. Add the ones you truly have.")
    elif worst == "requirements":
        bad = next((c["label"] for c in req_checks if not c["ok"]), "a requirement")
        nxt = f"The posting names {bad} and your resume doesn't show it. Add it if it's true, or know it may screen you out."
    else:
        bad = next((c["label"] for c in format_checks if not c["ok"]), "the layout")
        nxt = f"Fix the format check: {bad}."

    names = {"format": "Format", "keywords": "Key words", "requirements": "Requirements"}
    return {
        "score": score, "label": label_for(score), "next": nxt,
        "parts": [{"name": names[k], "score": round(100 * v) if v is not None else None, "weight": WEIGHTS[k] if v is not None else 0}
                  for k, v in parts.items()],
    }
