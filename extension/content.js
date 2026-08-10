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
    // Without this timeout, a lost response (e.g. the background
    // service worker getting terminated mid-request, which Chrome can
    // do if a request runs long -- Render's free-tier cold start after
    // idle can take 50+ seconds) hangs this Promise forever with zero
    // error, which is exactly what a stuck-on-"Loading..." sidebar with
    // no console error looks like. Racing against a timeout turns a
    // silent hang into a visible, actionable failure state instead.
    return Promise.race([
      new Promise((resolve) => chrome.runtime.sendMessage(message, resolve)),
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

  function injectSidebar() {
    if (document.getElementById("riseply-sidebar-host")) return null;

    const host = document.createElement("div");
    host.id = "riseply-sidebar-host";
    host.style.cssText = "position:fixed;top:16px;right:16px;z-index:2147483647;";
    document.documentElement.appendChild(host);
    const root = host.attachShadow({ mode: "open" });

    root.innerHTML = `
      <style>
        :host { all: initial; }
        .panel {
          all: initial;
          font-family: -apple-system, 'Inter', sans-serif;
          width: 300px;
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
      </style>
      <div class="panel">
        <div class="header">
          <span class="brand">Riseply</span>
          <button id="riseply-close" title="Hide">&times;</button>
        </div>
        <div class="body" id="riseply-body">
          <p class="hint">Loading…</p>
        </div>
      </div>
    `;

    root.getElementById("riseply-close").addEventListener("click", () => host.remove());
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
    `;

    renderUsage(root);

    root.getElementById("riseply-score-btn").addEventListener("click", async () => {
      const btn = root.getElementById("riseply-score-btn");
      btn.disabled = true;
      btn.textContent = "Scoring…";
      const result = await sendMessage({ type: "SCORE_JOB", ...job });
      btn.disabled = false;
      btn.textContent = "Score my resume";
      const slot = root.getElementById("riseply-score-slot");

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
      slot.innerHTML = filled.length
        ? `<p class="filled-list">Filled: ${filled.map(escapeHtml).join(", ")}.</p>`
        : `<p class="filled-list">Couldn't find matching fields on this page.</p>`;
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
    render(root, job);
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
      if (!document.getElementById("riseply-sidebar-host")) {
        log("sidebar host was removed from the DOM -- re-injecting");
        const root = injectSidebar();
        if (root) render(root, job);
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
