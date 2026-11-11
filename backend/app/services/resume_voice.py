"""Does this resume read like a person wrote it? Worked out without AI, from
patterns hiring managers and screeners now notice: stock phrases, every bullet
opening or sized the same way, em dashes, a headline that is a keyword pile.
Each flag says what to change. The fix is the existing "Make it sound more
human" button, which rewrites the wording and keeps every number and name."""
import re
import statistics
from collections import Counter

STOCK = ("results-driven", "results driven", "proven track record", "passionate", "dynamic", "team player",
         "synergy", "seamless", "seamlessly", "robust", "cutting-edge", "cutting edge", "fast-paced",
         "detail-oriented", "leveraged", "leveraging", "spearheaded", "utilized", "orchestrated", "best-in-class",
         "self-starter", "go-getter", "think outside the box")


def _lines(blocks: list[dict]) -> list[str]:
    return [(b.get("text") or "").strip() for b in blocks if b.get("type") in ("bullet", "text") and (b.get("text") or "").strip()]


def voice_flags(blocks: list[dict]) -> list[str]:
    flags: list[str] = []
    lines = _lines(blocks)
    bullets = [(b.get("text") or "").strip() for b in blocks if b.get("type") == "bullet" and (b.get("text") or "").strip()]
    joined = " ".join(lines).lower()

    hits = sorted({w for w in STOCK if re.search(rf"\b{re.escape(w)}\b", joined)})
    if len(hits) >= 2:
        flags.append("Stock phrases: " + ", ".join(hits[:4]) + ". Replace them with what you actually did.")

    openers = Counter(re.sub(r"[^a-z]", "", b.split()[0].lower()) for b in bullets if b.split())
    word, n = openers.most_common(1)[0] if openers else ("", 0)
    if n >= 3 and word:
        flags.append(f'{n} bullets start with "{word}". Vary how they open.')

    if len(bullets) >= 6:
        sizes = [len(b.split()) for b in bullets]
        if statistics.pstdev(sizes) < 3.0:
            flags.append("Every bullet is about the same length. Real work histories are uneven.")

    dashes = sum(l.count("—") + l.count(" -- ") for l in lines)
    if dashes >= 3:
        flags.append(f"{dashes} em dashes in the text. Use a comma, a period or \"and\".")

    head = next((b.get("text", "") for b in blocks if b.get("type") == "headline"), "")
    items = [x for x in re.split(r"[|,;]", head) if x.strip()]
    if len(items) >= 6:
        flags.append("The headline is a list of keywords. Keep a title and two or three skills.")
    return flags
