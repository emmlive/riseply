"""
GET /bookmarklet.js -- serves the actual autofill fill-logic as a real
JS file, authorized via a token query param rather than a normal
Bearer header (a <script src="..."> tag has no way to attach custom
headers, so a URL-embedded per-user token -- see
models.User.bookmarklet_token -- is the only practical way to identify
whose data to serve here).

This exists specifically to keep the BOOKMARKLET ITSELF tiny. The
previous design embedded the entire fill-logic function AND the
person's candidate data directly inline in the javascript: URI --
correct in principle, but the resulting URL measured over 5,500
characters for a typical profile, well past what many browsers'
bookmark-EDIT dialogs (a much more lightly-built UI component than
general URL navigation, which has no comparable practical limit)
reliably accept -- silently rejecting the paste, or silently failing
to create a bookmark at all via drag, with zero error shown either
way. The bookmarklet itself is now a short loader (see
frontend/lib/bookmarklet.ts) that injects a <script src> pointing
here; the actual logic and data live server-side and get fetched
fresh every time the bookmarklet runs, which also fixes a second,
separate problem the old design had: previously, updating your
profile required regenerating and reinstalling the bookmarklet, since
your data was permanently baked into it at generation time. Now it's
always current.
"""
from fastapi import APIRouter, Query, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session
import json

from app.database import get_db
from app import models

router = APIRouter(tags=["bookmarklet"])

# Kept in sync BY HAND with extension/content.js's runAutofill() field-
# matching logic (find-by-label, find-by-attr, first/last vs combined
# name, the location-SELECT skip fix) -- this is the bookmarklet's own
# independent implementation, not a shared module, since one runs as a
# Chrome extension content script and the other as an injected <script>
# tag on an arbitrary third-party page with no build step of its own.
FILL_LOGIC_JS = """
function riseplyFillLogic(data) {
  function setNativeValue(el, value) {
    var proto = Object.getPrototypeOf(el);
    var desc = Object.getOwnPropertyDescriptor(proto, "value");
    if (desc && desc.set) { desc.set.call(el, value); } else { el.value = value; }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }
  function findByLabelText(text) {
    var labels = document.querySelectorAll("label");
    for (var i = 0; i < labels.length; i++) {
      var l = labels[i];
      if ((l.textContent || "").toLowerCase().indexOf(text) !== -1) {
        var forId = l.getAttribute("for");
        if (forId) { var el = document.getElementById(forId); if (el) return el; }
        var inner = l.querySelector("input, textarea, select");
        if (inner) return inner;
      }
    }
    return null;
  }
  function findByAttr(text) {
    var els = document.querySelectorAll("input, textarea, select");
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var hay = ((el.getAttribute("aria-label") || "") + " " + (el.getAttribute("placeholder") || "") +
                 " " + (el.name || "") + " " + (el.id || "")).toLowerCase();
      if (hay.indexOf(text) !== -1) return el;
    }
    return null;
  }
  function find(text) { return findByLabelText(text) || findByAttr(text); }

  var filled = [];
  var firstEl = data.first ? find("first name") : null;
  var lastEl = data.last ? find("last name") : null;
  if (firstEl && data.first) { setNativeValue(firstEl, data.first); filled.push("first name"); }
  if (lastEl && data.last) { setNativeValue(lastEl, data.last); filled.push("last name"); }
  if (!firstEl && !lastEl && data.full) {
    var fullEl = find("full name") || find("name");
    if (fullEl) { setNativeValue(fullEl, data.full); filled.push("name"); }
  }

  var pairs = [
    ["email", data.email], ["phone", data.phone], ["location", data.location],
    ["linkedin", data.linkedin], ["website", data.website], ["portfolio", data.website],
  ];
  pairs.forEach(function (pair) {
    var label = pair[0], value = pair[1];
    if (!value) return;
    var el = find(label);
    if (!el) return;
    // See extension/content.js's identical fix -- a "location" SELECT
    // is far more likely a real office-location picker than a free-text
    // home-city field, and fuzzy-filling it with the candidate's raw
    // city text could silently choose the wrong office.
    if (label === "location" && el.tagName === "SELECT") return;
    setNativeValue(el, value);
    filled.push(label);
  });

  var msg = filled.length
    ? "Riseply auto-fill: filled " + filled.join(", ") + ". Attach your resume yourself " +
      "(browsers don't let scripts do that), then review everything before you submit."
    : "Riseply auto-fill: couldn't find matching fields on this page — fill this one manually.";
  alert(msg);
}
"""


def _error_script(message: str) -> str:
    """Always returns valid, executable JS -- even the error case --
    since a <script src> tag that 404s or returns malformed JS fails
    completely silently with nothing visible to the person at all. An
    alert() at least tells them something went wrong and roughly why.
    """
    return f"alert({json.dumps('Riseply auto-fill: ' + message)});"


@router.get("/bookmarklet.js")
def get_bookmarklet_script(token: str = Query(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(bookmarklet_token=token).first()
    if not user:
        # Deliberately vague -- doesn't distinguish "token never
        # existed" from "token was regenerated/invalidated" from
        # "wrong token entirely", since none of those distinctions
        # are useful to reveal to whoever is holding this URL, only
        # to the legitimate account holder who'd just regenerate a
        # fresh link from their own dashboard regardless of which
        # case it was.
        script = _error_script("this link is no longer valid. Go to your Riseply profile page for a fresh one.")
        return Response(content=script, media_type="application/javascript")

    name_parts = (user.full_name or "").strip().split(" ")
    first = name_parts[0] if name_parts and name_parts[0] else ""
    last = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
    data = {
        "first": first, "last": last, "full": user.full_name or "",
        "email": user.email or "", "phone": user.phone or "",
        "location": user.location or "", "linkedin": user.linkedin_url or "",
        "website": user.portfolio_url or "",
    }

    script = f"{FILL_LOGIC_JS}\nriseplyFillLogic({json.dumps(data)});"
    return Response(content=script, media_type="application/javascript")
