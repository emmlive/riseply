"""How far apart two places are, from a small bundled list of US cities.

Job boards write locations many ways ("Plainfield, IL", "Plainfield, Will County",
"Greater Chicago Area"), and a profile says "Chicago". To decide whether a job is
NEAR a search, both are turned into a point on the map and compared. The list
(app/geodata/us_places.json, towns of 5,000+ people from GeoNames, CC BY 4.0) is
loaded once on first use and is small. Anything that can't be placed returns
None so callers can fall back to simpler checks instead of guessing.
"""
import json
import math
import os
import re

_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "geodata", "us_places.json")
_data = None

_SUFFIX = re.compile(r"\b(greater|metropolitan|metro|area|region|united states|usa|u\.s\.a?\.?)\b|chicagoland", re.I)


def _load():
    global _data
    if _data is not None:
        return _data
    with open(_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    by_name: dict[str, list[tuple]] = {}
    for name, st, lat, lon, pop in raw["cities"]:
        by_name.setdefault(name.lower(), []).append((st, lat, lon, pop))
    counties: dict[str, set[str]] = {}
    for name, st in raw["counties"]:
        counties.setdefault(name.lower(), set()).add(st)
    states_by_name = {v.lower(): k for k, v in raw["states"].items()}
    _data = {"by_name": by_name, "counties": counties, "states": set(raw["states"]), "states_by_name": states_by_name}
    return _data


def _state_of(token: str) -> str | None:
    d = _load()
    t = token.strip().strip(".").lower()
    if len(t) == 2 and t.upper() in d["states"]:
        return t.upper()
    return d["states_by_name"].get(t)


def resolve(text: str) -> dict | None:
    """{"state": "IL", "lat": .., "lon": ..} for a city, {"state": "IL"} for a
    state on its own, or None when the place can't be recognised."""
    if not text:
        return None
    d = _load()
    cleaned = _SUFFIX.sub(" ", text)
    parts = [p.strip() for p in re.split(r"[,/|;]| - ", cleaned) if p.strip()]
    parts = [re.sub(r"\s+", " ", p) for p in parts]
    if not parts:
        return None

    # Which states does the text mention (directly, or through a county)?
    states: list[str] = []
    for p in parts[1:] + ([parts[0]] if len(parts) == 1 else []):
        st = _state_of(p)
        if st:
            states.append(st)
        m = re.match(r"(.+?)\s+(county|parish)$", p, re.I)
        if m:
            states += sorted(d["counties"].get(m.group(1).lower(), []))
    # "Chicago IL" with no comma
    m = re.match(r"(.+?)\s+([A-Za-z]{2})$", parts[0])
    city_part = parts[0]
    if m and _state_of(m.group(2)) and m.group(1).lower() in d["by_name"]:
        city_part, states = m.group(1), states + [_state_of(m.group(2))]

    cands = d["by_name"].get(city_part.lower().replace("saint ", "st. "), []) or d["by_name"].get(city_part.lower(), [])
    if cands:
        if states:
            narrowed = [c for c in cands if c[0] in states]
            if narrowed:
                cands = narrowed
            else:
                return {"state": states[0]}   # a city we don't list, in a known state
        best = max(cands, key=lambda c: c[3])
        return {"state": best[0], "lat": best[1], "lon": best[2]}
    st = _state_of(city_part) or (states[0] if states else None)
    return {"state": st} if st else None


def miles_between(a: dict, b: dict) -> float:
    r = 3958.8
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp, dl = p2 - p1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def is_near(search_places: list[str], job_place: str, radius_miles: float) -> bool | None:
    """True/False when both sides could be placed, None when they could not
    (so the caller keeps its older, simpler answer)."""
    job = resolve(job_place)
    if not job:
        return None
    judged = False
    for s in search_places:
        spot = resolve(s)
        if not spot:
            continue
        if "lat" in spot and "lat" in job:
            judged = True
            if miles_between(spot, job) <= radius_miles:
                return True
        elif spot.get("state") and job.get("state"):
            judged = True
            if spot["state"] == job["state"]:
                return True   # only a state is known on one side: same state is close enough to let the scorer decide
    return False if judged else None
