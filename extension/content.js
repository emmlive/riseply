// Riseply Autofill -- content script.
//
// Runs on every page (see manifest.json's <all_urls> match), but only
// actually does anything if the page looks like a job posting. Injects
// a sidebar via Shadow DOM so its styles can never leak into or be
// overridden by the host page's CSS.
//
// All Riseply API calls go through chrome.runtime.sendMessage to
// background.js -- see that file for why (CORS).

(function () {
  "use strict";

  // Consistent, greppable prefix -- filter the console for "[Riseply]"
  // to see exactly how far execution actually got, instead of
  // inferring it from visual behavior alone.
  function log(...args) {
    console.log("[Riseply]", ...args);
  }

  log("content script loaded on", location.href);

  window.addEventListener("beforeunload", () => log("page is unloading/navigating away"));
  window.addEventListener("pagehide", () => log("pagehide fired"));

  // Never show this on Riseply's own site -- most obviously wrong on
  // the Applications page, which isn't a job application FORM, it's a
  // list of your own applications, and clicking "autofill" there was
  // exactly the confusing dead-end the standalone bookmarklet hit
  // before this extension existed.
  if (/(^|\.)riseply\.(com|onrender\.com)$/.test(location.hostname)) {
    log("skipped: on Riseply's own domain");
    return;
  }

  // The job-or-not decision lives in jobdetect.js so it can be tested on its own.
  function looksLikeJobPage() {
    return window.RisePlyDetect ? window.RisePlyDetect.inspect() : { job: false, why: "detector missing" };
  }

  function findApplicationGateButton() {
    // Distinct from the narrow APPLY_PATTERN above (which is tuned to
    // avoid false-positiving on "Apply filters"/"Apply coupon" for
    // page-type DETECTION). This one is specifically for pointing a
    // person at their next click when autofill found zero fields --
    // Workday-style ATS sites commonly show a landing screen ("Start
    // Your Application", "Start Application", "Continue") before any
    // real form field exists at all, seen live more than once tonight.
    // A bit broader is fine here since a false match just offers an
    // extra button to click, not a change in what gets scored/filled.
    const GATE_PATTERN = /^(start (your )?application|start now|continue|apply now|begin)$/i;
    return Array.from(document.querySelectorAll("a, button")).find((el) =>
      GATE_PATTERN.test((el.textContent || "").trim())
    ) || null;
  }

  function findCoverLetterField() {
    // Looks specifically for a textarea labeled as a cover letter --
    // separate from the general custom-question detection, since this
    // is offered proactively via its own button rather than only
    // showing up when the field happens to already be empty and get
    // swept up in the general question scan.
    const COVER_LETTER_PATTERN = /cover letter/i;
    const textareas = document.querySelectorAll("textarea");
    for (const ta of textareas) {
      if (COVER_LETTER_PATTERN.test(getLabelForElement(ta))) return ta;
    }
    return null;
  }

  function scrapeJobInfo() {
    // Title, company and location come from jobinfo.js (structured data
    // first, then the best heading), because the first <h1> on many career
    // sites is just the company logo.
    const read = window.RisePlyJob ? window.RisePlyJob.read() : { title: (document.title || "").trim().slice(0, 300), company: "", location: "" };
    const { title, company } = read;

    // Blunt but robust across arbitrary site structures: the LLM doing
    // the actual scoring on the backend handles a somewhat noisy blob
    // of page text fine, and trying to precisely isolate "the job
    // description div" with a hand-written selector would break
    // constantly across the huge variety of ATS/career-page layouts.
    const description = (document.body?.innerText || "").trim().slice(0, 18000);

    return { title, company, location: read.location || "", description };
  }

  function sendMessage(message, timeoutMs = 15000) {
    // chrome.runtime.id disappears once this content script's context
    // has been invalidated -- the extension was reloaded (dev) or
    // Chrome auto-updated it (production) while this tab stayed open.
    // Calling chrome.runtime.sendMessage on a dead context throws
    // synchronously, which -- since the call sits inside a `new
    // Promise((resolve) => ...)` with no try/catch -- surfaces as an
    // unhandled promise rejection with a misleading stack trace rather
    // than a clean, actionable failure. Checking first avoids the
    // throw in the common case (extension reloaded during dev, or a
    // background auto-update landing on a real user's still-open tab).
    if (!chrome.runtime?.id) {
      log("extension context invalidated -- page needs a refresh");
      return Promise.resolve({
        success: false,
        error: "Riseply was updated. Please refresh this page.",
        contextInvalidated: true,
      });
    }

    // Without this timeout, a lost response (e.g. the background
    // service worker getting terminated mid-request, which Chrome can
    // do if a request runs long -- Render's free-tier cold start after
    // idle can take 50+ seconds) hangs this Promise forever with zero
    // error, which is exactly what a stuck-on-"Loading..." sidebar with
    // no console error looks like. Racing against a timeout turns a
    // silent hang into a visible, actionable failure state instead.
    return Promise.race([
      new Promise((resolve) => {
        try {
          chrome.runtime.sendMessage(message, (response) => {
            if (chrome.runtime.lastError) {
              // Covers the context dying in the gap between the check
              // above and the response actually coming back (e.g. an
              // update lands mid-flight) -- the background service
              // worker or its port is gone, so lastError is set instead
              // of a real response ever arriving.
              log("sendMessage lastError:", chrome.runtime.lastError.message);
              resolve({ success: false, error: "Riseply was updated. Please refresh this page.", contextInvalidated: true });
              return;
            }
            resolve(response);
          });
        } catch (err) {
          // Belt-and-suspenders: context can also die in the gap
          // between the check above and this call actually firing.
          log("sendMessage threw synchronously:", err.message);
          resolve({ success: false, error: "Riseply was updated. Please refresh this page.", contextInvalidated: true });
        }
      }),
      new Promise((resolve) =>
        setTimeout(() => {
          log("sendMessage timed out after", timeoutMs, "ms for", message.type);
          resolve({ success: false, error: "Riseply took too long to respond. The server may be waking up from idle -- try again in a moment." });
        }, timeoutMs)
      ),
    ]);
  }

  // --- Autofill (mirrors the bookmarklet's field-detection logic --
  // see frontend/lib/bookmarklet.ts -- but running directly in the
  // page's own DOM instead of through a javascript: URI, which is both
  // simpler and more reliable since there's no URI-encoding round trip) ---

  function setNativeValue(el, value) {
    const proto = Object.getPrototypeOf(el);
    const desc = Object.getOwnPropertyDescriptor(proto, "value");
    if (desc && desc.set) desc.set.call(el, value); else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function setSelectValue(select, desiredText) {
    // Selects don't take free text -- find the option whose visible
    // text (or value, as a fallback) actually contains what we're
    // looking for, case-insensitive substring match, same spirit as
    // the label matching above. Returns true only on an actual match;
    // never picks an arbitrary option just to fill something in.
    const target = desiredText.toLowerCase();
    for (const opt of select.options) {
      const hay = (opt.text || opt.value || "").toLowerCase();
      if (hay.includes(target)) {
        select.value = opt.value;
        select.dispatchEvent(new Event("input", { bubbles: true }));
        select.dispatchEvent(new Event("change", { bubbles: true }));
        return true;
      }
    }
    return false;
  }

  function setSelectValueExact(select, exactText) {
    // For AI-drafted select answers specifically -- already validated
    // server-side to be verbatim-identical to a real option, so an
    // EXACT match here (not the fuzzy substring match setSelectValue
    // above uses for the hardcoded "Mobile" default) avoids selecting
    // the wrong option when two options share overlapping text, e.g.
    // "Yes" vs. "Yes, but I will need visa sponsorship in the future"
    // -- substring matching on "Yes" could hit either one depending on
    // iteration order; exact matching can't.
    for (const opt of select.options) {
      if ((opt.text || "").trim() === exactText) {
        select.value = opt.value;
        select.dispatchEvent(new Event("input", { bubbles: true }));
        select.dispatchEvent(new Event("change", { bubbles: true }));
        return true;
      }
    }
    return false;
  }

  function fillElement(el, value) {
    // Single entry point runAutofill() calls regardless of whether the
    // matched field turned out to be a text input or a dropdown --
    // keeps the matching logic below from needing to know or care
    // which one it found.
    const before = el.value;
    let done = true;
    if (el.tagName === "SELECT") done = setSelectValue(el, value);
    else setNativeValue(el, value);
    if (done && window.RisePlyFill && el.value !== before) {
      window.RisePlyFill.record(el, getLabelForElement(el) || el.name || "Field", el.tagName === "SELECT" ? (el.selectedOptions[0]?.text || value) : value, before);
    }
    return done;
  }

  function findByLabelText(text) {
    const labels = document.querySelectorAll("label");
    for (const l of labels) {
      if ((l.textContent || "").toLowerCase().includes(text)) {
        const forId = l.getAttribute("for");
        if (forId) { const el = document.getElementById(forId); if (el) return el; }
        const inner = l.querySelector("input, textarea, select");
        if (inner) return inner;
      }
    }
    return null;
  }

  function findByAttr(text) {
    const els = document.querySelectorAll("input, textarea, select");
    for (const el of els) {
      const hay = (
        (el.getAttribute("aria-label") || "") + " " + (el.getAttribute("placeholder") || "") +
        " " + (el.name || "") + " " + (el.id || "")
      ).toLowerCase();
      if (hay.includes(text)) return el;
    }
    return null;
  }

  function findField(text) {
    return findByLabelText(text) || findByAttr(text);
  }

  function getLabelForElement(el) {
    // Reverse of findByLabelText -- given a field, find ITS label text,
    // rather than given text, find a matching field. Needed to identify
    // custom application questions (open-ended textareas the basic
    // profile-field autofill has nothing to match against) so they can
    // be surfaced for AI drafting instead of silently left blank with
    // no indication anything was missed.
    if (el.id) {
      const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (label) return (label.textContent || "").trim();
    }
    const wrappingLabel = el.closest("label");
    if (wrappingLabel) return (wrappingLabel.textContent || "").trim();
    // Fall back to the nearest preceding text-bearing element -- a very
    // common pattern (a <div>/<p> holding the question directly above
    // a plain <textarea> with no real <label> at all). Skips other
    // form controls explicitly -- an unrelated filled-in field's VALUE
    // is not a label, and walking into one would misread real answer
    // text as if it were the question itself.
    let sibling = el.previousElementSibling;
    let hops = 0;
    while (sibling && hops < 3) {
      const isFormControl = ["INPUT", "TEXTAREA", "SELECT", "BUTTON", "LABEL"].includes(sibling.tagName);
      const text = (sibling.textContent || "").trim();
      if (!isFormControl && text.length > 10) return text;
      sibling = sibling.previousElementSibling;
      hops++;
    }
    return el.getAttribute("aria-label") || el.getAttribute("placeholder") || "";
  }

  function isPlaceholderOptionText(text) {
    return /^(select( one)?|please select|choose( one)?|--+.*--+|)$/i.test((text || "").trim());
  }

  const SENSITIVE_PATTERN = /(\bauthoriz\w*\s+to\s+work\b|work\s+authoriz|eligib(le|ility)\s*to\s*work|\bvisa\b|sponsorship|\brace\b|ethnicit|gender identity|\bdisabilit|veteran|sexual orientation|protected class)/i;

  function detectUnansweredQuestions() {
    // Textareas: the clear, common case for open-ended application
    // questions ("Why do you want to work here?", "Describe a
    // challenging project"). Doesn't touch radio groups or custom
    // multi-choice widgets; those vary too much across sites to
    // handle safely in a first version.
    const questions = [];
    const textareas = document.querySelectorAll("textarea");
    for (const ta of textareas) {
      if ((ta.value || "").trim()) continue; // already has content -- don't touch it
      const label = getLabelForElement(ta);
      if (label.length > 10) {
        questions.push({ el: ta, question: label, isSelect: false, sensitive: SENSITIVE_PATTERN.test(label) });
      }
    }

    // Selects: dropdown application questions -- "How did you hear
    // about us?", pronouns, state/country, etc, as well as the
    // legally-significant ones (work authorization, sponsorship, EEOC
    // voluntary self-ID categories) that get flagged as sensitive
    // rather than ever auto-answered. See the sensitive-vs-safe design
    // note on the answer-question backend endpoint for why: resumes
    // essentially never state citizenship/visa status (people are
    // routinely advised to leave it off), so there's rarely anything
    // real to infer this from, and a wrong guess here can silently
    // submit a legally false statement or get someone auto-screened
    // out of a job they were actually eligible for.
    const selects = document.querySelectorAll("select");
    for (const sel of selects) {
      const selectedText = sel.selectedOptions[0]?.text || "";
      if (sel.value && !isPlaceholderOptionText(selectedText)) continue; // already answered -- don't touch it
      const label = getLabelForElement(sel);
      if (label.length <= 2) continue;
      const realOptions = Array.from(sel.options)
        .map((o) => o.text.trim())
        .filter((t) => t && !isPlaceholderOptionText(t));
      if (realOptions.length < 2) continue; // not a meaningful choice to make
      questions.push({ el: sel, question: label, isSelect: true, options: realOptions, sensitive: SENSITIVE_PATTERN.test(label) });
    }

    return questions;
  }

  // "EMMANUEL OGUNYINKA" and "emmanuel ogunyinka" become "Emmanuel Ogunyinka".
  // Names already in mixed case ("McDonald", "DeShawn") are left as typed.
  function properName(full) {
    const particles = new Set(["van", "von", "de", "del", "della", "der", "di", "da", "la", "le", "bin", "al", "dos", "du"]);
    const cap = (w) => w.toLowerCase().replace(/(^|[-'’.])([a-z])/g, (m, a, b) => a + b.toUpperCase());
    return String(full || "").trim().split(/\s+/).map((w, i, all) => {
      if (!/[a-z]/i.test(w)) return w;
      if (/^(ii|iii|iv)$/i.test(w)) return w.toUpperCase();
      if (/^(jr|sr)\.?$/i.test(w)) return w[0].toUpperCase() + w.slice(1).toLowerCase();
      if (w !== w.toUpperCase() && w !== w.toLowerCase()) return w;
      if (i > 0 && i < all.length - 1 && particles.has(w.toLowerCase())) return w.toLowerCase();
      return cap(w);
    }).join(" ");
  }

  // The "what did it just put where" list, with one button to take it back.
  function reviewHtml(items) {
    if (!items.length) return "";
    const rows = items.map((c) => `<li><span style="color:#2B3445;">${escapeHtml(c.label || "Field")}</span>: <strong>${escapeHtml(c.value)}</strong></li>`).join("");
    return `<div id="riseply-review" style="margin-top:8px;">
      <details><summary class="hint" style="cursor:pointer;font-weight:600;margin-top:0;">Review what was filled (${items.length})</summary>
        <ul class="hint" style="margin:4px 0 6px 16px;padding:0;max-height:180px;overflow:auto;">${rows}</ul>
      </details>
      <button class="action secondary" id="riseply-undo-btn" style="margin-top:4px;">Undo autofill</button>
    </div>`;
  }

  function runAutofill(candidate) {
    candidate = { ...candidate, full_name: properName(candidate.full_name) };
    const nameParts = (candidate.full_name || "").trim().split(" ");
    const first = nameParts[0] || "";
    const last = nameParts.slice(1).join(" ");
    const filled = [];

    const firstEl = first ? findField("first name") : null;
    const lastEl = last ? findField("last name") : null;
    if (firstEl && first && fillElement(firstEl, first)) filled.push("first name");
    if (lastEl && last && fillElement(lastEl, last)) filled.push("last name");
    if (!firstEl && !lastEl && candidate.full_name) {
      const fullEl = findField("full name") || findField("name");
      if (fullEl && fillElement(fullEl, candidate.full_name)) filled.push("name");
    }

    const pairs = [
      ["email", candidate.email], ["phone", candidate.phone], ["location", candidate.location],
      ["linkedin", candidate.linkedin_url], ["website", candidate.portfolio_url],
      ["portfolio", candidate.portfolio_url],
    ];
    for (const [label, value] of pairs) {
      if (!value) continue;
      const el = findField(label);
      if (!el) continue;
      // A field labeled "location" is ambiguous in a way none of the
      // other pairs above are: on a text input it's almost always
      // "your current city" (safe to fill with the candidate's home
      // location); on a SELECT it's much more often a controlled list
      // of real office locations to choose FROM ("which office are you
      // applying to"), completely unrelated to where the candidate
      // lives -- fuzzy substring-matching the candidate's raw city text
      // against that list (see setSelectValue) could silently pick the
      // wrong office with no indication anything went wrong. Only
      // skipped for this one label; the others don't have this
      // ambiguity (an email/phone/linkedin SELECT would be unusual
      // enough to not special-case).
      if (label === "location" && el.tagName === "SELECT") continue;
      if (fillElement(el, value)) filled.push(label);
    }

    return filled;
  }


  // --- Forms inside iframes ---
  // Some application systems (iCIMS, embedded Greenhouse) put the whole form in
  // an iframe. This script also runs in every sub-frame, but there it only
  // answers requests from the sidebar in the top frame (through background.js);
  // the sidebar itself is only ever shown once, in the top frame.

  function countFormControls() {
    return Array.from(document.querySelectorAll("input:not([type=hidden]):not([type=submit]):not([type=button]), select, textarea"))
      .filter((e) => e.offsetWidth || e.offsetHeight || e.getClientRects().length).length;
  }

  async function handleFrameOp(op, a) {
    const RF = window.RisePlyFill;
    if (!RF) return null;
    switch (op) {
      case "probe": {
        const adv = RF.findAdvance();
        return {
          host: location.hostname, fields: countFormControls(), login: RF.hasLogin(),
          file: RF.hasResumeInput(), advance: adv ? { label: adv.label, kind: adv.kind } : null,
        };
      }
      case "fill": {
        const filled = [];
        RF.resetChanges();
        if (a.candidate) filled.push(...runAutofill(a.candidate));
        if (a.login && RF.hasLogin() && RF.fillLogin(a.login).length) filled.push("site login");
        if (a.profile) {
          filled.push(...RF.run(a.profile).filled);
          filled.push(...(await RF.finishCustom()));
        }
        if (a.resume && RF.hasResumeInput() && RF.attachResume(a.resume, { replace: !!a.replace })) {
          filled.push(`${a.replace ? "ATS resume" : "resume"} (${a.resume.filename})`);
        }
        return { filled, left: RF.leftForYou(), changes: RF.changes() };
      }
      case "undo": return RF.undo();
      case "fillLogin": return RF.fillLogin(a.login);
      case "attach": return RF.attachResume(a.resume, { replace: true });
      case "advanceClick": {
        const now = RF.findAdvance(); // fresh: the page may have changed
        if (!now) return { clicked: false };
        now.el.click();
        return { clicked: true, label: now.label };
      }
      default: return null;
    }
  }

  function installFrameAgent() {
    if (/^(about|blob|data|javascript):$/.test(location.protocol)) return;
    try {
      chrome.runtime.onMessage.addListener((msg, _sender, send) => {
        if (!msg || msg.type !== "RF_OP") return;
        handleFrameOp(msg.op, msg.args || {}).then(send).catch((e) => send({ error: String((e && e.message) || e) }));
        return true;
      });
      chrome.runtime.sendMessage({ type: "FRAME_HELLO" }, () => void chrome.runtime.lastError);
    } catch (e) { /* extension context gone: nothing to do */ }
  }

  // Top frame: ask the sub-frames to do something. One answer per frame.
  async function frameOps(op, args, frameId, timeoutMs) {
    const r = await sendMessage({ type: "FRAME_OP", op, args: args || {}, frameId, timeoutMs }, (timeoutMs || 30000) + 5000);
    return r && r.success && Array.isArray(r.results) ? r.results.filter((x) => x.result && !x.result.error) : [];
  }

  // What the sub-frames hold right now (a sign-in box, an upload box, a Next
  // button). Refreshed every moment the sidebar checks the page.
  let frameState = [];
  async function refreshFrameState() {
    frameState = (await frameOps("probe", {}, undefined, 4000)).map((x) => ({ frameId: x.frameId, ...x.result }));
    return frameState;
  }
  function frameLogin() { return frameState.find((f) => f.login); }
  function frameAdvance() {
    const f = frameState.find((x) => x.advance);
    return f ? { label: f.advance.label, kind: f.advance.kind, frameId: f.frameId } : null;
  }
  // The site a sign-in box belongs to: this page's, or the iframe's that holds it.
  function currentLoginHost() {
    return window.RisePlyFill && window.RisePlyFill.hasLogin() ? location.hostname : (frameLogin() || {}).host || location.hostname;
  }
  function anyLogin() { return !!(window.RisePlyFill && window.RisePlyFill.hasLogin()) || !!frameLogin(); }
  function anyAdvance() { return (window.RisePlyFill && window.RisePlyFill.findAdvance()) || frameAdvance(); }
  async function fillLoginAnywhere(cred) {
    const done = window.RisePlyFill && window.RisePlyFill.hasLogin() ? window.RisePlyFill.fillLogin(cred) : [];
    for (const f of frameState.filter((x) => x.login)) {
      const r = await frameOps("fillLogin", { login: cred }, f.frameId, 8000);
      if (r[0] && Array.isArray(r[0].result)) done.push(...r[0].result);
    }
    return done;
  }
  async function attachAnywhere(payload) {
    if (window.RisePlyFill && window.RisePlyFill.attachResume(payload, { replace: true })) return true;
    await refreshFrameState();
    for (const f of frameState.filter((x) => x.file)) {
      const r = await frameOps("attach", { resume: payload }, f.frameId, 15000);
      if (r[0] && r[0].result === true) return true;
    }
    return false;
  }

  // --- Sidebar UI (Shadow DOM) ---

  const PANEL_STYLES = `
    :host { all: initial; }
    .panel {
      all: initial;
      font-family: -apple-system, 'Inter', sans-serif;
      width: 360px;
      background: #FFFFFF;
      border: 1px solid #E2E5EA;
      border-radius: 12px;
      box-shadow: 0 8px 30px rgba(22, 35, 61, 0.15);
      color: #16233D;
      display: block;
      overflow: hidden;
    }
    .header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 12px 14px; background: #1F7A6C; color: white;
    }
    .header .brand { font-weight: 700; font-size: 14px; display: flex; align-items: center; gap: 6px; }
    .header button {
      all: initial; cursor: pointer; color: white; font-size: 16px; line-height: 1;
      padding: 2px 6px; opacity: 0.85;
    }
    .header button:hover { opacity: 1; }
    .body { padding: 14px; font-size: 13px; max-height: calc(100vh - 170px); overflow-y: auto; }
    .job-title { font-weight: 600; margin: 0 0 2px 0; font-size: 13px; }
    .job-company { color: #5B6478; margin: 0 0 12px 0; font-size: 12px; }
    button.action {
      all: initial; box-sizing: border-box; display: block; width: 100%;
      text-align: center; padding: 9px 10px; border-radius: 8px; font-weight: 600;
      font-size: 13px; cursor: pointer; margin-bottom: 8px;
    }
    button.primary { background: #1F7A6C; color: white; }
    button.primary:hover { background: #17604F; }
    button.secondary { background: #E4F0EC; color: #17604F; }
    button.secondary:hover { background: #d5e8e1; }
    button.action:disabled { opacity: 0.6; cursor: default; }
    .score-box {
      background: #F5F6F8; border-radius: 8px; padding: 10px 12px; margin-bottom: 10px;
    }
    .score-pct { font-size: 20px; font-weight: 700; color: #1F7A6C; }
    .score-reason { font-size: 12px; color: #5B6478; margin-top: 4px; line-height: 1.4; }
    .hint { font-size: 11px; color: #5B6478; line-height: 1.4; margin-top: 8px; }
    .login-prompt { text-align: center; padding: 6px 0; }
    .login-prompt p { font-size: 12px; color: #5B6478; margin: 0 0 8px 0; }
    .filled-list { font-size: 11px; color: #5B6478; margin-top: 6px; }
    .draft-preview {
      all: initial; box-sizing: border-box; display: block; width: 100%;
      font-family: -apple-system, 'Inter', sans-serif; font-size: 12px; color: #16233D;
      border: 1px solid #E2E5EA; border-radius: 8px; padding: 8px; margin-top: 6px;
      resize: vertical; background: #FFFFFF;
    }
    .field {
      all: initial; box-sizing: border-box; display: block; width: 100%;
      font-family: -apple-system, 'Inter', sans-serif; font-size: 12px; color: #16233D;
      border: 1px solid #E2E5EA; border-radius: 6px; padding: 6px 8px; margin-top: 6px; background: #FFFFFF;
    }
    .draft-actions { display: flex; gap: 6px; margin-top: 6px; }
    .draft-actions button {
      all: initial; box-sizing: border-box; flex: 1; text-align: center; padding: 6px 8px;
      border-radius: 6px; font-weight: 600; font-size: 12px; cursor: pointer;
      font-family: -apple-system, 'Inter', sans-serif;
    }
    .draft-actions .confirm { background: #1F7A6C; color: white; }
    .draft-actions .confirm:hover { background: #17604F; }
    .draft-actions .discard { background: #F5F6F8; color: #5B6478; }
    .draft-actions .discard:hover { background: #e9ebee; }
    .minimized-btn {
      all: initial; box-sizing: border-box; display: flex; align-items: center;
      justify-content: center; width: 44px; height: 44px; border-radius: 12px;
      background: #1F7A6C; color: white; font-weight: 700; font-size: 15px;
      cursor: pointer; box-shadow: 0 4px 16px rgba(22, 35, 61, 0.2);
      font-family: -apple-system, 'Inter', sans-serif;
    }
    .minimized-btn:hover { background: #17604F; }
  `;

  function expandPanel(root, job) {
    // Rebuilds the full header+body panel and re-wires the close
    // button to minimize (not remove) -- called both on first inject
    // and any time the person clicks the minimized icon to reopen.
    root.innerHTML = `
      <style>${PANEL_STYLES}</style>
      <div class="panel">
        <div class="header">
          <span class="brand">Riseply</span>
          <button id="riseply-close" title="Minimize">&times;</button>
        </div>
        <div class="body" id="riseply-body">
          <p class="hint">Loading…</p>
        </div>
      </div>
    `;
    root.getElementById("riseply-close").addEventListener("click", () => minimizePanel(root, job));
    if (job) render(root, job);
  }

  function minimizePanel(root, job) {
    // Collapses to a small persistent icon rather than removing the
    // sidebar entirely -- matches how other job-search extensions
    // (Simplify, Jobright) stay reachable via a small docked icon
    // instead of vanishing without a way back short of a page reload.
    root.innerHTML = `
      <style>${PANEL_STYLES}</style>
      <button class="minimized-btn" id="riseply-reopen" title="Open Riseply">R</button>
    `;
    root.getElementById("riseply-reopen").addEventListener("click", () => expandPanel(root, job));
  }

  function injectSidebar() {
    if (document.getElementById("riseply-sidebar-host")) return null;

    const host = document.createElement("div");
    host.id = "riseply-sidebar-host";
    // Offset from the very top-right corner deliberately -- top:16/
    // right:16 is the same generic slot most extensions default to
    // (confirmed directly: it was stacking right on top of Simplify's
    // own card). No way to know at runtime exactly where other
    // installed extensions position theirs, but landing further down
    // meaningfully cuts down on exact collisions in practice.
    host.style.cssText = "position:fixed;top:90px;right:16px;z-index:2147483647;";
    document.documentElement.appendChild(host);
    const root = host.attachShadow({ mode: "open" });
    expandPanel(root, null); // job isn't known yet -- init() calls expandPanel() again once it's scraped
    return root;
  }

  async function render(root, job) {
    log("render() starting, checking auth state...");
    const bodyEl = root.getElementById("riseply-body");
    const auth = await sendMessage({ type: "GET_AUTH_STATE" });
    log("GET_AUTH_STATE resolved:", auth);

    if (!auth.loggedIn) {
      const timedOut = auth.success === false || auth.unreachable === true;
      log(timedOut ? "auth check timed out" : "not logged in", "-- showing prompt");
      bodyEl.innerHTML = `
        <p class="job-title">${escapeHtml(job.title)}</p>
        <p class="job-company">${escapeHtml(job.company)}</p>
        <div class="login-prompt">
          <p>${timedOut ? escapeHtml(auth.error) : "Log in to Riseply from the toolbar icon to see your match score and autofill this page."}</p>
        </div>
      `;
      return;
    }

    log("logged in -- rendering full sidebar for", auth.user?.email);
    bodyEl.innerHTML = `
      <p class="job-title">${escapeHtml(job.title)}</p>
      <p class="job-company">${escapeHtml(job.company)}</p>
      <div id="riseply-usage-slot"></div>
      <div id="riseply-score-slot"></div>
      <button class="action primary" id="riseply-score-btn">Score my resume</button>
      <div id="riseply-tailor-slot"></div>
      <button class="action secondary" id="riseply-fill-btn">Autofill this page</button>
      <p class="hint">Autofill attaches your resume when the form has an upload field, and fills the rest. Check everything before you continue. Riseply never submits on its own -- you always get a final button to click yourself.</p>
      <div id="riseply-login-slot"></div>
      <div id="riseply-filled-slot"></div>
      <div id="riseply-next-slot"></div>
      <div id="riseply-applied-slot"></div>
      <div id="riseply-questions-slot"></div>
      <button class="action secondary" id="riseply-coverletter-btn" style="margin-top:12px;">Generate cover letter</button>
      <div id="riseply-coverletter-slot"></div>
    `;

    renderUsage(root);
    renderLogin(root);
    renderNext(root);
    refreshJobStatus(root);
    // Pages change without reloading (sign-in, then the form, then the next
    // step), so keep these two sections in step with what is on the page now.
    let lastSeen = "";
    let checking = false;
    setInterval(async () => {
      if (checking) return;
      checking = true;
      try {
        await refreshFrameState();
        const adv = anyAdvance();
        const sig = (anyLogin() ? "L" : "-") + (adv ? adv.label : "");
        if (sig !== lastSeen) { lastSeen = sig; renderLogin(root); renderNext(root); }
      } finally { checking = false; }
    }, 1500);

    root.getElementById("riseply-score-btn").addEventListener("click", async () => {
      const btn = root.getElementById("riseply-score-btn");
      const slot = root.getElementById("riseply-score-slot");
      // Re-scrape fresh at click time rather than reusing the job
      // object captured once when the page first loaded -- SPA-heavy
      // sites (Workday/Salesforce-style pages, seen live) can still be
      // rendering their real title/description well after the page
      // technically "loaded", and by the time someone actually clicks
      // a button, meaningfully more time has passed.
      const freshJob = scrapeJobInfo();
      if (!freshJob.title.trim() || !freshJob.description.trim()) {
        slot.innerHTML = `<p class="hint" style="color:#B23B3B;">Couldn't read this page's job details yet -- try again in a moment, or refresh the page.</p>`;
        return;
      }
      btn.disabled = true;
      btn.textContent = "Scoring…";
      const result = await sendMessage({ type: "SCORE_JOB", ...freshJob });
      btn.disabled = false;
      btn.textContent = "Score my resume";

      if (!result.success) {
        // Scoring shares the same monthly "match" quota as the regular
        // "Find new matches" button in the app -- a 429 here means
        // that shared limit is hit, not something specific to the
        // extension, so the message and upgrade path should match what
        // the web app would show in the same situation.
        if (result.status === 429) {
          slot.innerHTML = `
            <div class="score-box" style="background:#FBEEE0;">
              <div class="score-reason" style="color:#C97A2B;">
                Monthly match limit reached. <a href="https://riseply.com/dashboard/billing" target="_blank" style="color:#C97A2B;font-weight:600;">Upgrade to Pro</a> for a higher limit.
              </div>
            </div>
          `;
        } else {
          slot.innerHTML = `<p class="hint" style="color:#B23B3B;">${escapeHtml(result.error || "Couldn't score this job.")}</p>`;
        }
        return;
      }
      slot.innerHTML = `
        <div class="score-box">
          <div class="score-pct">${result.score}% match</div>
          <div class="score-reason">${escapeHtml(result.reason || "")}</div>
        </div>
      `;
      renderUsage(root); // refresh the count after a successful, quota-consuming score
    });

    root.getElementById("riseply-fill-btn").addEventListener("click", async () => {
      const btn = root.getElementById("riseply-fill-btn");
      btn.disabled = true;
      btn.textContent = "Filling…";
      const result = await sendMessage({ type: "GET_CANDIDATE" });
      btn.disabled = false;
      btn.textContent = "Autofill this page";
      const slot = root.getElementById("riseply-filled-slot");
      if (!result.success) {
        slot.innerHTML = `<p class="hint" style="color:#B23B3B;">${escapeHtml(result.error || "Couldn't load your profile.")}</p>`;
        return;
      }
      if (window.RisePlyFill) window.RisePlyFill.resetChanges();
      const filled = runAutofill(result.candidate);
      if (window.RisePlyFill && window.RisePlyFill.hasLogin()) {
        const sl = await sendMessage({ type: "GET_SITE_LOGIN", host: location.hostname });
        if (sl.success && sl.login && window.RisePlyFill.fillLogin(sl.login).length) filled.push("site login");
      }
      // Work history, education, standard answers and saved answers come from
      // the person's Autofill profile. If it can't be loaded, basic autofill
      // above still stands.
      let profileHint = "";
      const prof = await sendMessage({ type: "GET_AUTOFILL_PROFILE" });
      const tailored = pageApp && pageApp.has_tailored ? pageApp.application_id : null;
      let resumeFile = null; // fetched once, whichever frame has the upload box
      const getResume = async () => {
        if (!resumeFile) resumeFile = await sendMessage({ type: "GET_RESUME_FILE", applicationId: tailored });
        return resumeFile;
      };
      if (prof.success && window.RisePlyFill) {
        if (window.RisePlyFill.isEmptyProfile(prof.profile)) {
          profileHint = `<p class="hint" style="margin-top:8px;">Add your work history and common answers once, and Autofill will use them: <a href="https://riseply.com/dashboard/autofill-profile" target="_blank" style="color:inherit;font-weight:600;">Set up your Autofill profile</a>.</p>`;
        }
        filled.push(...window.RisePlyFill.run(prof.profile).filled);
        // Pick-from-a-list questions (country, state, Yes/No dropdowns) are
        // answered one at a time; this can take a few seconds.
        btn.textContent = "Filling lists…";
        filled.push(...(await window.RisePlyFill.finishCustom()));
        // Attach the resume if the form has an upload field. Skipped quietly
        // when it fails: the person can still drag the file in themselves.
        if (window.RisePlyFill.hasResumeInput()) {
          const rf = await getResume();
          if (rf.success && window.RisePlyFill.attachResume(rf, { replace: !!tailored })) filled.push(`${tailored ? "ATS resume" : "resume"} (${rf.filename})`);
        }
      }
      // The same again inside any iframes on the page (iCIMS, embedded
      // Greenhouse): the form there is out of this frame's reach.
      let frameLeft = [];
      let frameChanges = [];
      const filledFrames = [];
      await refreshFrameState();
      const formFrames = frameState.filter((f) => f.fields > 0 || f.login || f.file);
      if (formFrames.length) {
        btn.textContent = "Filling the form…";
        const rf = formFrames.some((f) => f.file) && prof.success ? await getResume() : null;
        const answers = await Promise.all(formFrames.map(async (f) => {
          let login = null;
          if (f.login) {
            const sl = await sendMessage({ type: "GET_SITE_LOGIN", host: f.host });
            login = sl.success && sl.login ? sl.login : null;
          }
          const r = await frameOps("fill", {
            candidate: result.candidate, login, profile: prof.success ? prof.profile : null,
            resume: rf && rf.success ? rf : null, replace: !!tailored,
          }, f.frameId, 60000);
          return r[0] ? r[0].result : null;
        }));
        for (const a of answers) {
          if (!a) continue;
          filled.push(...(a.filled || []));
          frameLeft.push(...(a.left || []));
          frameChanges.push(...(a.changes || []));
        }
        formFrames.forEach((f, i) => { if (answers[i] && (answers[i].changes || []).length) filledFrames.push(f.frameId); });
      }
      const uniqueFilled = Array.from(new Set(filled));
      const reviewItems = (window.RisePlyFill ? window.RisePlyFill.changes() : []).concat(frameChanges);
      const left = (window.RisePlyFill ? window.RisePlyFill.leftForYou() : []).concat(frameLeft);
      // Remember what Autofill couldn't answer, so the person can answer it once
      // in Riseply and the product can learn what to support. Question text only.
      if (left.length) sendMessage({ type: "LOG_UNANSWERED", questions: left, host: location.hostname }, 8000);
      const leftHtml = left.length
        ? `<p class="hint" style="margin-top:8px;"><strong>Still for you (${left.length}):</strong></p><ul class="hint" style="margin:2px 0 0 16px;padding:0;">${left.map((q) => `<li>${escapeHtml(q)}</li>`).join("")}</ul>`
        : "";
      if (uniqueFilled.length) {
        slot.innerHTML = `
          <p class="filled-list">Filled: ${uniqueFilled.map(escapeHtml).join(", ")}.</p>
          ${reviewHtml(reviewItems)}
          ${leftHtml}
          <p class="hint" style="margin-top:4px;">Fields you had already filled were left alone. Questions you haven't answered in your Autofill profile are left for you. Need another job or school? Add the section on the form and press Autofill again.</p>
          ${profileHint}
        `;
      } else {
        const gateBtn = findApplicationGateButton();
        if (gateBtn) {
          slot.innerHTML = `
            <p class="filled-list">This looks like a landing page, not the application form yet.</p>
            <button class="action secondary" id="riseply-gate-btn" style="margin-top:6px;">Go to the application →</button>
          `;
          root.getElementById("riseply-gate-btn").addEventListener("click", () => {
            // Human-initiated either way: the person clicked THIS
            // button first, deliberately, to reach the real form --
            // this just saves them hunting for the page's own button
            // rather than silently clicking anything on their behalf
            // without them choosing to.
            gateBtn.click();
          });
        } else {
          slot.innerHTML = `<p class="filled-list">Couldn't find matching fields on this page.</p>${leftHtml}`;
        }
      }

      const undoBtn = root.getElementById("riseply-undo-btn");
      if (undoBtn) {
        undoBtn.addEventListener("click", async () => {
          undoBtn.disabled = true;
          const r = window.RisePlyFill ? window.RisePlyFill.undo() : { undone: 0, manual: 0 };
          let undone = r.undone, manual = r.manual;
          for (const id of filledFrames) {
            const fr = await frameOps("undo", {}, id, 15000);
            if (fr[0] && fr[0].result) { undone += fr[0].result.undone || 0; manual += fr[0].result.manual || 0; }
          }
          const rev = root.getElementById("riseply-review");
          if (rev) rev.innerHTML = `<p class="hint">Undone: ${undone} ${undone === 1 ? "answer" : "answers"} cleared.${manual ? ` ${manual} pick-from-a-list ${manual === 1 ? "choice was" : "choices were"} not reset; change ${manual === 1 ? "it" : "them"} on the form.` : ""} Press Autofill again to refill.</p>`;
        });
      }

      renderLogin(root);
      renderNext(root);
      renderUnansweredQuestions(root, scrapeJobInfo()); // fresh scrape -- see the Score button's handler for why
    });

    root.getElementById("riseply-coverletter-btn").addEventListener("click", async () => {
      const btn = root.getElementById("riseply-coverletter-btn");
      const clSlot = root.getElementById("riseply-coverletter-slot");
      btn.disabled = true;
      btn.textContent = "Generating…";
      const result = await sendMessage({ type: "GENERATE_COVER_LETTER", ...scrapeJobInfo() });
      btn.disabled = false;
      btn.textContent = "Generate cover letter";

      if (!result.success) {
        if (result.status === 429) {
          clSlot.innerHTML = `<p class="hint" style="color:#C97A2B;margin-top:6px;">Monthly limit reached. <a href="https://riseply.com/dashboard/billing" target="_blank" style="color:#C97A2B;font-weight:600;">Upgrade to Pro</a></p>`;
        } else {
          clSlot.innerHTML = `<p class="hint" style="color:#B23B3B;margin-top:6px;">${escapeHtml(result.error || "Couldn't generate a cover letter.")}</p>`;
        }
        return;
      }

      // Same confirm-before-touching-the-page pattern as question
      // drafting: editable preview here first, nothing written to the
      // real page until explicitly confirmed. If there's no actual
      // cover-letter field on this page (most sites just want a
      // file upload, which can't be auto-attached -- same hard
      // browser restriction as the resume), copy-to-clipboard is
      // always available as the fallback so generating is still
      // useful even then.
      const coverLetterEl = findCoverLetterField();
      clSlot.innerHTML = `
        <textarea class="draft-preview" id="riseply-cl-text" rows="8">${escapeHtml(result.cover_letter)}</textarea>
        <div class="draft-actions">
          ${coverLetterEl ? `<button class="confirm" id="riseply-cl-use">Use this — fill the field</button>` : ""}
          <button class="discard" id="riseply-cl-copy">Copy to clipboard</button>
        </div>
      `;

      if (coverLetterEl) {
        root.getElementById("riseply-cl-use").addEventListener("click", () => {
          const finalText = root.getElementById("riseply-cl-text").value;
          setNativeValue(coverLetterEl, finalText);
          clSlot.insertAdjacentHTML("beforeend", `<p class="filled-list">✓ Filled the cover letter field.</p>`);
        });
      }
      root.getElementById("riseply-cl-copy").addEventListener("click", async () => {
        const text = root.getElementById("riseply-cl-text").value;
        const copyBtn = root.getElementById("riseply-cl-copy");
        try {
          await navigator.clipboard.writeText(text);
          copyBtn.textContent = "Copied ✓";
          setTimeout(() => { copyBtn.textContent = "Copy to clipboard"; }, 2000);
        } catch {
          // Clipboard API can be blocked in some contexts -- the
          // textarea right above is still selectable/copyable by hand,
          // so this failure isn't a dead end, just a missed shortcut.
        }
      });
    });
  }

  function renderUnansweredQuestions(root, job) {
    const slot = root.getElementById("riseply-questions-slot");
    const questions = detectUnansweredQuestions();
    if (questions.length === 0) {
      slot.innerHTML = "";
      return;
    }

    slot.innerHTML = `
      <p class="hint" style="margin-top:12px;font-weight:600;color:#16233D;">
        ${questions.length} application question${questions.length !== 1 ? "s" : ""} still need${questions.length === 1 ? "s" : ""} an answer
      </p>
      ${questions.map((q, i) => `
        <div style="margin-top:6px;padding:8px 10px;background:#F5F6F8;border-radius:8px;">
          <p class="hint" style="margin:0 0 6px;color:#16233D;">${escapeHtml(q.question.slice(0, 140))}${q.question.length > 140 ? "…" : ""}</p>
          ${q.sensitive
            ? `<p class="hint" style="color:#C97A2B;margin:0;">⚠️ Needs your own answer -- not auto-filled on purpose.</p>`
            : `<button class="action secondary" id="riseply-answer-btn-${i}" style="margin:0;padding:6px 10px;font-size:12px;">Draft with AI</button>
               <div id="riseply-answer-preview-${i}"></div>`
          }
        </div>
      `).join("")}
    `;

    questions.forEach((q, i) => {
      if (q.sensitive) return; // no button was rendered for these -- see the note above
      const btn = root.getElementById(`riseply-answer-btn-${i}`);
      const previewSlot = root.getElementById(`riseply-answer-preview-${i}`);

      btn.addEventListener("click", async () => {
        btn.disabled = true;
        btn.textContent = "Drafting…";
        const result = await sendMessage({
          type: "ANSWER_QUESTION", question: q.question,
          options: q.isSelect ? q.options : undefined,
          ...job,
        });
        btn.disabled = false;
        btn.textContent = "Draft with AI";

        if (!result.success) {
          if (result.status === 429) {
            previewSlot.innerHTML = `<p class="hint" style="color:#C97A2B;margin-top:6px;">Monthly limit reached. <a href="https://riseply.com/dashboard/billing" target="_blank" style="color:#C97A2B;font-weight:600;">Upgrade to Pro</a></p>`;
          } else {
            previewSlot.innerHTML = `<p class="hint" style="color:#B23B3B;margin-top:6px;">${escapeHtml(result.error || "Couldn't draft an answer.")}</p>`;
          }
          return;
        }

        if (q.isSelect) {
          if (result.answer === "UNKNOWN") {
            previewSlot.innerHTML = `<p class="hint" style="margin-top:6px;">Couldn't confidently determine an answer -- please pick manually.</p>`;
            return;
          }
          // Confirm step before touching the real page, per the
          // explicit design decision -- see the same reasoning on the
          // cover letter flow below.
          previewSlot.innerHTML = `
            <p class="hint" style="margin-top:6px;">AI suggests: <strong>${escapeHtml(result.answer)}</strong></p>
            <div class="draft-actions">
              <button class="confirm" id="riseply-confirm-${i}">Use this answer</button>
              <button class="discard" id="riseply-discard-${i}">Discard</button>
            </div>
          `;
          root.getElementById(`riseply-confirm-${i}`).addEventListener("click", () => {
            if (setSelectValueExact(q.el, result.answer)) {
              previewSlot.innerHTML = `<p class="filled-list">✓ Answered.</p>`;
              btn.style.display = "none";
            } else {
              previewSlot.innerHTML = `<p class="hint" style="color:#B23B3B;">Couldn't set that option -- please pick manually.</p>`;
            }
          });
          root.getElementById(`riseply-discard-${i}`).addEventListener("click", () => { previewSlot.innerHTML = ""; });
        } else {
          // Editable preview, not an immediate fill -- the person can
          // tweak the draft right here before it ever touches the
          // real page, then explicitly confirms. Since that review now
          // genuinely happens (not just a marker string left in the
          // field), there's no need for the old inline "[AI-drafted --
          // review before submitting]" prefix on the final text
          // anymore -- the confirm step IS the review.
          previewSlot.innerHTML = `
            <textarea class="draft-preview" id="riseply-draft-text-${i}" rows="4">${escapeHtml(result.answer)}</textarea>
            <div class="draft-actions">
              <button class="confirm" id="riseply-confirm-${i}">Use this answer</button>
              <button class="discard" id="riseply-discard-${i}">Discard</button>
            </div>
          `;
          root.getElementById(`riseply-confirm-${i}`).addEventListener("click", () => {
            const finalText = root.getElementById(`riseply-draft-text-${i}`).value;
            setNativeValue(q.el, finalText);
            previewSlot.innerHTML = `<p class="filled-list">✓ Answered.</p>`;
            btn.style.display = "none";
          });
          root.getElementById(`riseply-discard-${i}`).addEventListener("click", () => { previewSlot.innerHTML = ""; });
        }
        // Deliberately NOT calling renderUsage() here -- it only shows
        // the shared match quota, but drafting an answer consumes the
        // separate interview_prep quota instead. Calling it here would
        // misleadingly imply match quota was spent when it wasn't.
      });
    });
  }


  // Sign-in: the person saves a username and password for a site once; they
  // stay in this browser only (never sent to Riseply) and are filled on that
  // site's own sign-in form when the person asks.
  async function renderLogin(root) {
    const slot = root.getElementById("riseply-login-slot");
    if (!slot) return;
    if (!window.RisePlyFill || !anyLogin()) { slot.innerHTML = ""; return; }
    const loginHost = currentLoginHost();
    const r = await sendMessage({ type: "GET_SITE_LOGIN", host: loginHost });
    const site = (r && r.site) || loginHost;
    if (r && r.success && r.login) {
      slot.innerHTML = `
        <p class="filled-list" style="margin-top:12px;">Saved login for ${escapeHtml(site)}: ${escapeHtml(r.login.username)}</p>
        <button class="action secondary" id="riseply-login-fill" style="margin-top:6px;">Fill my login</button>
        <p class="hint"><a href="#" id="riseply-login-change" style="color:inherit;font-weight:600;">Change</a> &nbsp; <a href="#" id="riseply-login-forget" style="color:inherit;font-weight:600;">Forget</a></p>
        <div id="riseply-login-msg"></div>
      `;
      root.getElementById("riseply-login-fill").addEventListener("click", async () => {
        const done = await fillLoginAnywhere(r.login);
        root.getElementById("riseply-login-msg").innerHTML = done.length
          ? `<p class="filled-list">Filled: ${done.join(", ")}. Check it, then use the button below.</p>`
          : `<p class="hint">Those boxes already have something in them, so nothing changed.</p>`;
        renderNext(root);
      });
      root.getElementById("riseply-login-forget").addEventListener("click", async (e) => {
        e.preventDefault();
        await sendMessage({ type: "FORGET_SITE_LOGIN", host: currentLoginHost() });
        renderLogin(root);
      });
      root.getElementById("riseply-login-change").addEventListener("click", (e) => {
        e.preventDefault();
        showLoginForm(root, slot, site);
      });
    } else {
      showLoginForm(root, slot, site);
    }
  }

  function showLoginForm(root, slot, site) {
    slot.innerHTML = `
      <p class="hint" style="margin-top:12px;"><strong>Save your login for ${escapeHtml(site)}</strong> so Riseply can fill it next time. It stays in this browser only and is never sent to Riseply.</p>
      <input class="field" id="riseply-login-user" type="text" placeholder="Username or email" autocomplete="off">
      <input class="field" id="riseply-login-pass" type="password" placeholder="Password" autocomplete="off">
      <button class="action secondary" id="riseply-login-save" style="margin-top:6px;">Save on this device</button>
      <div id="riseply-login-msg"></div>
    `;
    root.getElementById("riseply-login-save").addEventListener("click", async () => {
      const username = root.getElementById("riseply-login-user").value.trim();
      const password = root.getElementById("riseply-login-pass").value;
      const res = await sendMessage({ type: "SAVE_SITE_LOGIN", host: currentLoginHost(), username, password });
      if (!res.success) {
        root.getElementById("riseply-login-msg").innerHTML = `<p class="hint" style="color:#B23B3B;">${escapeHtml(res.error || "Couldn't save.")}</p>`;
        return;
      }
      renderLogin(root);
    });
  }

  // "Next page" / "Log in" / "Submit": clicks the site's own button, but only
  // after the person confirms. Submit is final, so it says so.
  function renderNext(root) {
    const slot = root.getElementById("riseply-next-slot");
    if (!slot) return;
    const adv = anyAdvance();
    if (!adv) { slot.innerHTML = ""; return; }
    const kind = adv.kind || (/log ?in|sign ?in/i.test(adv.label) ? "login" : "next");
    const title = kind === "login" ? "Log in" : kind === "submit" ? "Submit application" : "Next page";
    slot.innerHTML = `
      <button class="action primary" id="riseply-next-btn" style="margin-top:10px;">${title} →</button>
      <div id="riseply-next-confirm"></div>
    `;
    root.getElementById("riseply-next-btn").addEventListener("click", () => {
      const c = root.getElementById("riseply-next-confirm");
      c.innerHTML = `
        <p class="hint" style="color:#C97A2B;">This clicks ${escapeHtml(location.hostname)}'s own "${escapeHtml(adv.label)}" button. ${kind === "submit" ? "Make sure your resume is attached and everything looks right. This can't be undone." : "Check what's filled in first."}</p>
        <div class="draft-actions">
          <button class="confirm" id="riseply-next-yes">${kind === "submit" ? "Yes, submit" : "Yes, go on"}</button>
          <button class="discard" id="riseply-next-no">Cancel</button>
        </div>
      `;
      root.getElementById("riseply-next-yes").addEventListener("click", async () => {
        if (adv.frameId != null) {
          await frameOps("advanceClick", {}, adv.frameId, 8000);
        } else {
          const now = window.RisePlyFill.findAdvance(); // fresh: the page may have changed
          if (now) now.el.click();
        }
        if (kind === "submit") {
          c.innerHTML = `<p class="filled-list">Clicked the site's submit button.</p>`;
          renderApplied(root, true);
        } else {
          c.innerHTML = `<p class="filled-list">Clicked "${escapeHtml(adv.label)}". When the next page loads, press Autofill again.</p>`;
        }
      });
      root.getElementById("riseply-next-no").addEventListener("click", () => { c.innerHTML = ""; });
    });
  }

  // What Riseply already knows about the job on this page: in the person's
  // list or not, tailored resume or not, applied or not.
  let pageApp = null;

  function pageUrl() { return location.href.split("#")[0]; }

  async function refreshJobStatus(root) {
    const r = await sendMessage({ type: "JOB_STATUS", url: pageUrl() });
    pageApp = r && r.success && r.in_list ? r : null;
    renderTailor(root);
    renderApplied(root, false);
  }

  function atsSummary(t) {
    const checks = t.ats || [];
    if (!checks.length) return "";
    const bad = checks.filter((c) => !c.ok);
    return `<p class="hint">ATS checks: ${checks.length - bad.length} of ${checks.length} passed.${bad.map((c) => ` ${escapeHtml(c.detail)}`).join("")}</p>`;
  }

  function renderTailor(root, fresh) {
    const slot = root.getElementById("riseply-tailor-slot");
    if (!slot) return;
    const link = `<a href="https://riseply.com/dashboard/applications" target="_blank" style="color:inherit;font-weight:600;">Review or edit it in Riseply</a>`;
    if (pageApp && pageApp.has_tailored) {
      slot.innerHTML = `
        <p class="filled-list" style="margin-top:10px;">ATS resume ready for this job.</p>
        ${fresh && fresh.rationale ? `<p class="hint">${escapeHtml(fresh.rationale)}</p>` : ""}
        ${fresh ? atsSummary(fresh) : ""}
        <button class="action secondary" id="riseply-attach-btn" style="margin-top:6px;">Attach it to this form</button>
        <p class="hint">Autofill attaches it too. ${link}.</p>
        <div id="riseply-attach-msg"></div>
      `;
      root.getElementById("riseply-attach-btn").addEventListener("click", async () => {
        const msg = root.getElementById("riseply-attach-msg");
        const rf = await sendMessage({ type: "GET_RESUME_FILE", applicationId: pageApp.application_id });
        if (rf.success && window.RisePlyFill && await attachAnywhere(rf)) {
          msg.innerHTML = `<p class="filled-list">Attached ${escapeHtml(rf.filename)}.</p>`;
        } else {
          msg.innerHTML = `<p class="hint">I couldn't find a resume upload box on this page yet. Open the application form and press this again.</p>`;
        }
      });
      return;
    }
    slot.innerHTML = `
      <button class="action secondary" id="riseply-tailor-btn" style="margin-top:6px;">Generate ATS resume</button>
      <p class="hint">Rewrites your resume around this job's wording in a plain, one-column layout. It uses only what is already in your resume. Counts as one tailored resume this month.</p>
      <div id="riseply-tailor-msg"></div>
    `;
    root.getElementById("riseply-tailor-btn").addEventListener("click", async () => {
      const btn = root.getElementById("riseply-tailor-btn");
      const msg = root.getElementById("riseply-tailor-msg");
      const job = scrapeJobInfo();
      if (!job.title.trim() || job.description.trim().length < 80) {
        msg.innerHTML = `<p class="hint" style="color:#B23B3B;">I can't read this job's details on this page. Open the job posting, then press this again.</p>`;
        return;
      }
      btn.disabled = true;
      btn.textContent = "Generating… about 30 seconds";
      const t = await sendMessage({ type: "TAILOR_RESUME", ...job, url: pageUrl() }, 150000);
      btn.disabled = false;
      btn.textContent = "Generate ATS resume";
      if (!t.success) {
        msg.innerHTML = t.status === 429
          ? `<p class="hint" style="color:#C97A2B;">You've used this month's limit. <a href="https://riseply.com/dashboard/billing" target="_blank" style="color:#C97A2B;font-weight:600;">Upgrade to Pro</a> for more.</p>`
          : `<p class="hint" style="color:#B23B3B;">${escapeHtml(t.error || "Couldn't generate it right now. Try again shortly.")}</p>`;
        return;
      }
      pageApp = t;
      if (!t.has_tailored) {
        msg.innerHTML = `<p class="hint" style="color:#C97A2B;">${escapeHtml(t.notes || "The resume wasn't generated this time. Try again from Applications in Riseply.")}</p>`;
        return;
      }
      renderTailor(root, t);
      renderApplied(root, false);
      renderUsage(root);
    });
  }

  // After the person has applied: record it on Riseply, but only for a job in
  // their Riseply list. Always their click; never automatic.
  function renderApplied(root, justSubmitted) {
    const slot = root.getElementById("riseply-applied-slot");
    if (!slot) return;
    if (!pageApp) {
      slot.innerHTML = justSubmitted
        ? `<p class="hint">This job isn't in your Riseply list, so there is nothing to mark. Generate an ATS resume for it first if you want it tracked.</p>`
        : "";
      return;
    }
    if (pageApp.applied) {
      slot.innerHTML = `<p class="filled-list" style="margin-top:10px;">Marked as applied on Riseply.</p>`;
      return;
    }
    slot.innerHTML = `
      <p class="hint" style="margin-top:10px;">${justSubmitted ? "Did the application go through?" : "Done on the employer's site?"}</p>
      <button class="action secondary" id="riseply-applied-btn" style="margin-top:4px;">I've applied: mark it on Riseply</button>
      <div id="riseply-applied-msg"></div>
    `;
    root.getElementById("riseply-applied-btn").addEventListener("click", async () => {
      const r = await sendMessage({ type: "MARK_APPLIED", applicationId: pageApp.application_id, url: pageUrl() });
      if (r.success && r.found) {
        pageApp.applied = true;
        renderApplied(root, false);
      } else {
        root.getElementById("riseply-applied-msg").innerHTML = `<p class="hint" style="color:#B23B3B;">${escapeHtml(r.error || "Couldn't update Riseply. Try again.")}</p>`;
      }
    });
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  async function renderUsage(root) {
    const slot = root.getElementById("riseply-usage-slot");
    if (!slot) return;
    const usage = await sendMessage({ type: "GET_USAGE" });
    if (!usage.success) return; // non-critical -- just skip showing it rather than surfacing an error for this

    const nearLimit = usage.matchesUsed >= usage.matchesLimit * 0.9;
    slot.innerHTML = `
      <p class="hint" style="margin-top:0;margin-bottom:8px;${nearLimit ? "color:#C97A2B;" : ""}">
        ${usage.matchesUsed}/${usage.matchesLimit} matches used this month (${usage.tier === "pro" ? "Pro" : "Free"})
        ${usage.tier !== "pro" ? ' · <a href="https://riseply.com/dashboard/billing" target="_blank" style="color:inherit;">Upgrade</a>' : ""}
      </p>
    `;
  }

  function init() {
    log("init() running, readyState:", document.readyState);
    const verdict = looksLikeJobPage();
    log("job page?", verdict.job, "-", verdict.why);
    if (!verdict.job) return;
    const root = injectSidebar();
    log("injectSidebar() returned:", root ? "a shadow root" : "null (already existed?)");
    if (!root) return;
    const job = scrapeJobInfo();
    log("scraped job info:", job.title, "@", job.company);
    // expandPanel (not render directly) -- re-wires the close button's
    // closure with the real job (injectSidebar() itself only knew
    // null when it first built the panel), so a later minimize->reopen
    // cycle doesn't get stuck on "Loading..." from render() never
    // being called with a null job.
    expandPanel(root, job);
    watchForRemoval(job);
  }

  // Heavy single-page-app frameworks (this page is a React app, and its
  // own console shows real hydration errors -- #418/#425/#423) can wipe
  // out DOM nodes they don't recognize during a re-render or error-
  // recovery pass, even ones attached outside their own root (this
  // sidebar is appended to <html> directly, deliberately outside
  // React's render tree, specifically to avoid that -- but "flashed
  // and disappeared" is exactly what losing that race looks like).
  // Rather than trying to out-guess every framework's internal timing,
  // just watch for the host element vanishing and put it back.
  function watchForRemoval(job) {
    const observer = new MutationObserver(() => {
      if (!chrome.runtime?.id) {
        // Context is dead (extension reloaded/updated under this open
        // tab) -- re-injecting a sidebar at this point would just
        // produce a panel that can never talk to the background
        // script again. Stop watching; a page refresh is what actually
        // fixes it, per the message sendMessage() now surfaces.
        log("extension context invalidated -- stopping DOM watch");
        observer.disconnect();
        return;
      }
      if (!document.getElementById("riseply-sidebar-host")) {
        log("sidebar host was removed from the DOM -- re-injecting");
        const root = injectSidebar();
        // expandPanel (not render directly) -- injectSidebar() itself
        // calls expandPanel(root, null) since it doesn't know the job
        // yet, which wires the close button's closure to a null job.
        // Re-calling expandPanel here with the REAL job re-wires that
        // closure correctly, so a later minimize->reopen cycle on this
        // restored panel doesn't get stuck on "Loading..." forever
        // from render() never being called with a null job.
        if (root) expandPanel(root, job);
      }
    });
    observer.observe(document.documentElement, { childList: true });
    log("watching for removal");
  }

  if (window !== window.top) {
    installFrameAgent();
  } else if (document.readyState === "complete" || document.readyState === "interactive") {
    init();
  } else {
    document.addEventListener("DOMContentLoaded", init);
  }
})();
