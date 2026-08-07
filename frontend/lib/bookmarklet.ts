/**
 * Generates a "bookmarklet" -- a javascript: URI the person drags to
 * their bookmarks bar -- that fills common application-form fields on
 * whatever page they currently have open, using their own Riseply
 * profile info.
 *
 * Why this exists instead of server-side automation: the old approach
 * ran Playwright headless on the backend, which can never hand off to
 * the person's own browser window -- there's no session, no visible
 * page, nothing left for them to review or finish. A bookmarklet runs
 * IN their browser, on the actual page they're looking at, which is
 * the only way to genuinely give control back to them afterward.
 *
 * Real limitation, stated up front rather than glossed over: browsers
 * do not allow a script to programmatically set a file input's value
 * (a hard security restriction, not a bug here) -- so this can fill
 * text fields (name, email, phone, location, links) but the person
 * still has to manually attach their resume via the file picker. The
 * on-page message this generates says so explicitly.
 */

export interface AutoFillCandidate {
  full_name: string;
  email: string;
  phone: string;
  location: string;
  linkedin_url: string;
  portfolio_url: string;
}

// This function's *source* (not its behavior here) is what gets shipped
// into the bookmarklet -- it never runs in this app's own page context.
// Keep it self-contained: no closures over anything outside its own
// body except the `data` object injected right before it.
function fillLogic(data: {
  first: string; last: string; full: string;
  email: string; phone: string; location: string;
  linkedin: string; website: string;
}) {
  function setNativeValue(el: any, value: string) {
    const proto = Object.getPrototypeOf(el);
    const desc = Object.getOwnPropertyDescriptor(proto, "value");
    if (desc && desc.set) {
      desc.set.call(el, value);
    } else {
      el.value = value;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function findByLabelText(text: string): any {
    const labels = document.querySelectorAll("label");
    for (let i = 0; i < labels.length; i++) {
      const l = labels[i];
      if ((l.textContent || "").toLowerCase().indexOf(text) !== -1) {
        const forId = l.getAttribute("for");
        if (forId) {
          const el = document.getElementById(forId);
          if (el) return el;
        }
        const inner = l.querySelector("input, textarea");
        if (inner) return inner;
      }
    }
    return null;
  }

  function findByAttr(text: string): any {
    const els = document.querySelectorAll("input, textarea");
    for (let i = 0; i < els.length; i++) {
      const el = els[i] as HTMLInputElement;
      const hay = (
        (el.getAttribute("aria-label") || "") + " " +
        (el.getAttribute("placeholder") || "") + " " +
        (el.name || "") + " " + (el.id || "")
      ).toLowerCase();
      if (hay.indexOf(text) !== -1) return el;
    }
    return null;
  }

  function find(text: string): any {
    return findByLabelText(text) || findByAttr(text);
  }

  const filled: string[] = [];

  // Two name conventions exist across ATS platforms -- split first/last
  // fields (Greenhouse/Lever) vs one combined field (Ashby/Workable).
  // Check which pattern is actually present before deciding what to
  // fill, same reasoning as the old server-side filler.
  const firstEl = data.first ? find("first name") : null;
  const lastEl = data.last ? find("last name") : null;
  if (firstEl && data.first) { setNativeValue(firstEl, data.first); filled.push("first name"); }
  if (lastEl && data.last) { setNativeValue(lastEl, data.last); filled.push("last name"); }
  if (!firstEl && !lastEl && data.full) {
    const fullEl = find("full name") || find("name");
    if (fullEl) { setNativeValue(fullEl, data.full); filled.push("name"); }
  }

  const pairs: [string, string][] = [
    ["email", data.email], ["phone", data.phone], ["location", data.location],
    ["linkedin", data.linkedin], ["website", data.website], ["portfolio", data.website],
  ];
  pairs.forEach(([label, value]) => {
    if (!value) return;
    const el = find(label);
    if (el) { setNativeValue(el, value); filled.push(label); }
  });

  const msg = filled.length
    ? "Riseply auto-fill: filled " + filled.join(", ") + ". Attach your resume yourself " +
      "(browsers don't let scripts do that), then review everything before you submit."
    : "Riseply auto-fill: couldn't find matching fields on this page — fill this one manually.";
  alert(msg);
}

export function buildAutoFillBookmarklet(candidate: AutoFillCandidate): string {
  const nameParts = (candidate.full_name || "").trim().split(" ");
  const first = nameParts[0] || "";
  const last = nameParts.slice(1).join(" ");

  const data = {
    first, last, full: candidate.full_name || "",
    email: candidate.email || "", phone: candidate.phone || "",
    location: candidate.location || "", linkedin: candidate.linkedin_url || "",
    website: candidate.portfolio_url || "",
  };

  // fillLogic.toString() gives us its full source as text -- this is
  // what actually ships into the bookmarklet, not a description of it.
  const script = `(function(){var data=${JSON.stringify(data)};(${fillLogic.toString()})(data);})();`;
  return "javascript:" + encodeURIComponent(script);
}
