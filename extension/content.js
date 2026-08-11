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

  const ATS_HOSTS = [
    "greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com",
    "smartrecruiters.com", "jobvite.com", "icims.com", "taleo.net",
    "breezy.hr", "workable.com", "bamboohr.com", "recruitee.com",
  ];
  const JOB_URL_HINTS = ["/jobs/", "/job/", "/careers/", "/career/", "/viewjob", "/positions/", "/vacancy/"];

  function looksLikeJobPage() {
    const host = location.hostname.toLowerCase();
    const path = location.pathname.toLowerCase();

    if (ATS_HOSTS.some((h) => host.endsWith(h))) return true;
    if (JOB_URL_HINTS.some((hint) => path.includes(hint))) return true;

    // Generic fallback: a page with a prominent "Apply" control and a
    // meaningful amount of body text is very likely a job posting even
    // on a site not on the known-ATS list (a company's own in-house
    // careers page, for instance). Deliberately narrow -- "Apply
    // filters", "Apply coupon", "Apply changes" all start with the word
    // "apply" too, and would false-positive on any sufficiently long
    // page (a blog post with a filter sidebar, an e-commerce checkout)
    // without this being specific about what "apply" actually means.
    const APPLY_PATTERN = /^apply\s*(now|for this (job|position|role|opening))?\s*$/i;
    const applyEl = Array.from(document.querySelectorAll("a, button")).find((el) =>
      APPLY_PATTERN.test((el.textContent || "").trim())
    );
    const bodyTextLength = (document.body?.innerText || "").length;
    return Boolean(applyEl) && bodyTextLength > 1500;
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
    const h1 = document.querySelector("h1");
    const title = (h1?.textContent || document.title || "").trim().slice(0, 300);

    const ogSite = document.querySelector('meta[property="og:site_name"]')?.content;
    const company = (ogSite || location.hostname.replace(/^(www|jobs|careers|boards)\./, "").split(".")[0] || "")
      .trim().slice(0, 200);

    // Blunt but robust across arbitrary site structures: the LLM doing
    // the actual scoring on the backend handles a somewhat noisy blob
    // of page text fine, and trying to precisely isolate "the job
    // description div" with a hand-written selector would break
    // constantly across the huge variety of ATS/career-page layouts.
    const description = (document.body?.innerText || "").trim().slice(0, 18000);

    return { title, company, location: "", description };
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
    if (el.tagName === "SELECT") return setSelectValue(el, value);
    setNativeValue(el, value);
    return true;
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

  function runAutofill(candidate) {
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
      if (el && fillElement(el, value)) filled.push(label);
    }

    // Fields with no corresponding profile data at all (Riseply doesn't
    // ask "what type of phone do you have"), but where a safe,
    // universal default genuinely applies -- deliberately narrow, and
    // called out explicitly in the result so it's never mistaken for
    // real personal data being filled.
    const phoneTypeEl = findField("phone type") || findField("device type");
    if (phoneTypeEl && phoneTypeEl.tagName === "SELECT" && setSelectValue(phoneTypeEl, "mobile")) {
      filled.push("phone type (defaulted to Mobile)");
    }

    return filled;
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
    .body { padding: 14px; font-size: 13px; }
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
      const timedOut = auth.success === false;
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
      <button class="action secondary" id="riseply-fill-btn">Autofill this page</button>
      <p class="hint">Autofill can't attach your resume or submit for you -- browsers block scripts from doing either, on purpose. Fill in fields, then finish it yourself.</p>
      <div id="riseply-filled-slot"></div>
      <div id="riseply-questions-slot"></div>
      <button class="action secondary" id="riseply-coverletter-btn" style="margin-top:12px;">Generate cover letter</button>
      <div id="riseply-coverletter-slot"></div>
    `;

    renderUsage(root);

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
      const filled = runAutofill(result.candidate);
      if (filled.length) {
        slot.innerHTML = `<p class="filled-list">Filled: ${filled.map(escapeHtml).join(", ")}.</p>`;
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
          slot.innerHTML = `<p class="filled-list">Couldn't find matching fields on this page.</p>`;
        }
      }

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
    const isJob = looksLikeJobPage();
    log("looksLikeJobPage():", isJob);
    if (!isJob) return;
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

  if (document.readyState === "complete" || document.readyState === "interactive") {
    init();
  } else {
    document.addEventListener("DOMContentLoaded", init);
  }
})();
