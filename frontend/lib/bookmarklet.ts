/**
 * Generates a "bookmarklet" -- a javascript: URI the person drags to
 * their bookmarks bar (or copy-pastes in) -- that fills common
 * application-form fields on whatever page they currently have open,
 * using their own Riseply profile info.
 *
 * LOADER PATTERN, not an inline bookmarklet -- and this distinction is
 * load-bearing, not stylistic. An earlier version embedded the entire
 * fill-logic function AND the person's candidate data directly inline
 * in the javascript: URI. That measured well over 5,500 characters for
 * a typical profile -- past what many browsers' bookmark-EDIT dialogs
 * (a much more lightly-built UI component than general URL navigation,
 * which has no comparable practical limit) reliably accept. Confirmed
 * live: pasting it produced an empty URL field, and dragging it
 * created no bookmark at all -- both silent failures, no error shown
 * either way, exactly what "I can't get either one to work" looks
 * like from the outside.
 *
 * This version is a tiny loader (well under 200 characters) that
 * injects a <script src="{API_URL}/bookmarklet.js?token=..."> tag at
 * click time -- the actual fill logic and the person's CURRENT profile
 * data live server-side (see backend/app/routers/bookmarklet.py) and
 * get served fresh every time it runs. This also fixes a second,
 * separate problem the old design had: previously, updating your
 * profile required regenerating and reinstalling the bookmarklet,
 * since data was baked in at generation time. Now it's always current
 * -- the token identifies WHO you are, not a frozen snapshot of your
 * profile.
 *
 * Real limitation, unchanged from before and stated up front rather
 * than glossed over: browsers do not allow a script to programmatically
 * set a file input's value (a hard security restriction, not a bug
 * here) -- so this can fill text fields (name, email, phone, location,
 * links) but the person still has to manually attach their resume via
 * the file picker. The alert this generates says so explicitly.
 */

export function buildAutoFillBookmarklet(bookmarkletToken: string, apiUrl: string): string {
  // Deliberately minimal -- every extra character here is exactly the
  // kind of bulk that caused the original design's length problem.
  // Cache-busted with Date.now() so a stale cached copy of
  // bookmarklet.js never masks a profile update -- scripts loaded via
  // a dynamically-injected <script> tag can otherwise be served from
  // the browser's HTTP cache even when the underlying data changed.
  const script =
    `(function(){var s=document.createElement('script');` +
    `s.src='${apiUrl}/bookmarklet.js?token=${bookmarkletToken}&t='+Date.now();` +
    `document.body.appendChild(s);})();`;
  return "javascript:" + encodeURIComponent(script);
}
