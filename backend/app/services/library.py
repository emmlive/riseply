"""Library retrieval and the coach's recommendation protocol.

The Career Coach may recommend Library items, but only by id: the prompt
lists the (few) relevant items with their ids, the model marks a
recommendation with [[lib:ID]], and the backend (a) drops any marker whose
id wasn't in the list it was offered, and (b) resolves surviving markers
into real Library rows at read time. The model never sees or writes a URL,
so it has no way to invent a link, and a deleted/deactivated item simply
stops appearing. Retrieval reuses the platform KB's keyword scorer --
same trade-off as there (no embeddings infrastructure; fine for a library
in the dozens-to-hundreds range).
"""
import re

from app import models
from app.services.kb import _score_items

MARKER_RE = re.compile(r"\[\[lib:(\d+)\]\]")
_MARKER_WITH_SPACE_RE = re.compile(r"[ \t]*\[\[lib:\d+\]\]")


def tags(item: models.LibraryItem) -> list[str]:
    return [t for t in (item.fields or "").split(",") if t]


def retrieve(items: list[models.LibraryItem], query: str, limit: int = 4) -> list[models.LibraryItem]:
    """Active items ranked by keyword overlap with the query (tags count
    toward the title, which the scorer weights double). Empty if nothing
    overlaps -- callers treat that as 'nothing to recommend'."""
    active = [i for i in items if i.active]
    scored = _score_items(
        query,
        [(f"{i.title} {' '.join(tags(i))}", i.description or "") for i in active],
        min_score=1,
    )
    return [active[idx] for idx, _ in scored[:limit]]


def prompt_block(offered: list[models.LibraryItem]) -> str:
    """The Library section of a coach prompt. Deliberately omits URLs."""
    rules = """LIBRARY -- EXTRA LEARNING:
You may point the person to the Riseply Library resources listed below
when it would genuinely help: they showed a knowledge gap, asked how to
learn something, or you're closing out a topic. Rules:
- Recommend ONLY items from this list, at most two per message, and only
  when one clearly fits. Right after naming a resource, add its marker
  exactly like [[lib:ID]] (the number in brackets below). The app turns
  the marker into a link card.
- Never write URLs, and never name or describe any course, book, site, or
  certification that isn't in this list. If nothing in the list fits, say
  so plainly and describe the KIND of resource worth looking for instead
  (no specific names).
- Don't recommend something just to recommend something; most messages
  need none. Never interrupt a mock interview with one."""
    if not offered:
        return rules + "\n\nAvailable resources: (none relevant right now -- do not recommend any)"
    lines = [
        f"[ID {i.id}] {i.title} -- {i.resource_type}, {i.cost}, {i.level} level. "
        f"{(i.description or '').strip()} (topics: {', '.join(tags(i)) or 'general'})"
        for i in offered
    ]
    return rules + "\n\nAvailable resources:\n" + "\n".join(lines)


def strip_unoffered_markers(text: str, offered_ids: set[int]) -> str:
    """Write-time guard: remove any [[lib:ID]] the model produced for an
    id it wasn't offered (a hallucinated or stale id)."""
    def keep(m: re.Match) -> str:
        return m.group(0) if int(m.group(1)) in offered_ids else ""
    return MARKER_RE.sub(keep, text)


def resolve(text: str, items_by_id: dict[int, models.LibraryItem]) -> tuple[str, list[models.LibraryItem]]:
    """Read-time: returns (text with markers removed, the distinct active
    items it referenced, in order of first mention)."""
    found: list[models.LibraryItem] = []
    for m in MARKER_RE.finditer(text):
        item = items_by_id.get(int(m.group(1)))
        if item and item.active and item not in found:
            found.append(item)
    return _MARKER_WITH_SPACE_RE.sub("", text).strip(), found
