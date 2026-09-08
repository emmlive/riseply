// Lets a super admin (User.is_admin) temporarily preview the
// individual/personal dashboard experience without actually changing
// their account's real org affiliation -- a client-side-only display
// override, never touches the database. Useful for QA and demos: a
// super admin who also administers an org (or is an org employee)
// would otherwise never see what a plain individual user's nav and
// Overview page look like, since that's normally computed entirely
// from real account data with no way to preview the other state.
//
// Deliberately NOT gated in this file itself -- every call site is
// responsible for checking user?.is_admin before honoring this flag,
// since a plain org admin or employee has no legitimate reason to
// bypass their own account's real, intentional nav restrictions this
// way. This is a staff QA tool, not a general user preference.
//
// localStorage (not a server-side setting) is deliberately right here:
// this is a personal, this-browser-only, non-critical display
// preference for one staff member's own testing -- not application
// data that needs to sync across devices or be visible to anyone else.
const STORAGE_KEY = "riseply_preview_as_individual";

export function isPreviewingAsIndividual(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(STORAGE_KEY) === "1";
}

export function setPreviewAsIndividual(value: boolean) {
  if (typeof window === "undefined") return;
  if (value) {
    window.localStorage.setItem(STORAGE_KEY, "1");
  } else {
    window.localStorage.removeItem(STORAGE_KEY);
  }
}
