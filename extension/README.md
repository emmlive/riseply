# Riseply Autofill (Chrome Extension)

Not published to the Chrome Web Store yet — this is loaded locally in
Developer Mode for testing. See the main README for the plan to
publish later.

## Install (Developer Mode)

1. Open Chrome, go to `chrome://extensions`.
2. Toggle **Developer mode** on (top right).
3. Click **Load unpacked**.
4. Select this `extension/` folder.
5. You should see "Riseply Autofill" appear in your extensions list
   with the green Riseply icon. Pin it to the toolbar for easy access
   (puzzle-piece icon → pin).

## Using it

1. Click the toolbar icon, log in with your Riseply account (same
   email/password as riseply.com).
2. Go to any job posting page — a Greenhouse/Lever/Ashby/Workday
   posting, or most companies' own in-house careers pages.
3. A sidebar should appear in the top-right with the detected job
   title/company, a "Score my resume" button, and an "Autofill this
   page" button.

## What to actually check (this is real-browser-only — I couldn't
verify any of this myself)

- Does the sidebar actually appear on real job pages you visit?
- Does it correctly **not** appear on non-job pages (news sites, your
  own Riseply dashboard, random browsing)?
- Does "Score my resume" return a sensible score and reason?
- Does "Autofill this page" actually fill in real fields on a real
  application form? Which fields does it miss?
- Any console errors? Right-click the sidebar → Inspect (or check the
  page's DevTools console) if something looks broken.

## Known limitations (by design, not bugs to fix)

- Can't attach your resume to the file input — browsers block scripts
  from setting a file input's value, on purpose. Same limitation as
  the bookmarklet.
- Can't click Submit for you — same reasoning, this fills fields, you
  review and submit.
- The generic "looks like a job page" fallback (for sites not on the
  known-ATS list) is a heuristic, not perfect — it may miss some real
  job pages or occasionally show up somewhere unexpected. Worth
  reporting back what you see so the heuristic can be tuned.

## Reloading after code changes

Every time the code changes, go back to `chrome://extensions` and
click the refresh icon on the Riseply Autofill card — Chrome doesn't
auto-reload unpacked extensions.

## Publishing later (not done yet)

To get the one-click "Install" experience from riseply.com, this needs
to go through the Chrome Web Store: a one-time $5 developer account
fee, then Google reviews the submission (usually a few days) before it
goes live. Until then, this only works via the manual Developer Mode
install above.
