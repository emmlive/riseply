// Riseply Autofill -- background service worker.
//
// All API calls to Riseply happen HERE, not in content.js. Manifest V3
// background service workers are exempt from page-level CORS
// enforcement for hosts listed in host_permissions (manifest.json) --
// content scripts, which run inside the page's own context, are NOT
// exempt. Routing every fetch through this file (via chrome.runtime
// messaging from content.js and popup.js) is what makes this work
// reliably across arbitrary job sites without touching backend CORS
// config at all.

const API_BASE = "https://riseply.onrender.com";

// Site a saved login belongs to: the registrable domain, so a login saved on
// jobs.example.com also works on apply.example.com but not on example.com.evil.net.
function siteKey(host) {
  const parts = String(host || "").toLowerCase().split(".").filter(Boolean);
  if (parts.length <= 2) return parts.join(".");
  const secondLevel = ["co", "com", "org", "net", "gov", "ac", "edu"];
  const n = parts[parts.length - 1].length === 2 && secondLevel.includes(parts[parts.length - 2]) ? 3 : 2;
  return parts.slice(-n).join(".");
}

function log(...args) {
  console.log("[Riseply:bg]", ...args);
}

async function getToken() {
  const { riseply_token } = await chrome.storage.local.get("riseply_token");
  return riseply_token || null;
}

function formatErrorDetail(detail) {
  // FastAPI/Pydantic validation errors return detail as an ARRAY of
  // {loc, msg, type, ...} objects, not a string -- seen live: a raw
  // JSON dump of that array was showing up directly in the sidebar
  // ("[{type:string_too_short,...}]"), which is exactly the kind of
  // internal-implementation-detail leak a person should never see.
  // Extracts just the human-readable msg from each entry instead.
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((d) => (d && typeof d === "object" && typeof d.msg === "string") ? d.msg : null)
      .filter(Boolean);
    return messages.length ? messages.join("; ") : "Something about this request wasn't valid.";
  }
  return "Something went wrong.";
}

async function apiFetch(path, options = {}) {
  const token = await getToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  log("fetching", path, "...");
  const start = Date.now();
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  log(path, "responded with status", res.status, "after", Date.now() - start, "ms");

  const isJson = (res.headers.get("content-type") || "").includes("application/json");
  const body = isJson ? await res.json() : null;

  if (!res.ok) {
    const detail = body?.detail || `Request failed (${res.status})`;
    const error = new Error(formatErrorDetail(detail));
    error.status = res.status;
    throw error;
  }
  return body;
}


// ---- Apply queue ("next job") ----
// The person's best matches, opened one at a time in a tab. A floating bar on
// each page (queuebar.js) offers Autofill, "I applied, next" and Skip. The
// person always clicks the employer's own Submit; nothing here submits. State
// lives in session storage so it survives the service worker sleeping.
const QUEUE_KEY = "riseply_queue";
async function getQueue() { return (await chrome.storage.session.get(QUEUE_KEY))[QUEUE_KEY] || null; }
async function setQueue(q) {
  if (q) await chrome.storage.session.set({ [QUEUE_KEY]: q });
  else await chrome.storage.session.remove(QUEUE_KEY);
}
function safeUrl(u) { return /^https?:\/\//i.test(String(u || "")) ? String(u) : ""; }
async function openInQueueTab(q, url) {
  const target = safeUrl(url);
  if (!target) throw new Error("This job has no usable link.");
  try {
    await chrome.tabs.update(q.tabs[0], { url: target });
  } catch (e) {
    const tab = await chrome.tabs.create({ url: target });
    q.tabs = [tab.id];
  }
  q.tabs = [q.tabs[0]];   // pages the person opened from the job lose the bar once we move on
}
function queueView(q, tabId) {
  const item = q.items[q.index] || null;
  return { success: true, active: !!(item && q.tabs.includes(tabId)), index: q.index, total: q.items.length,
           item, applied: q.applied, skipped: q.skipped };
}
chrome.tabs.onCreated.addListener(async (tab) => {
  // An Apply link that opens the employer's page in a new tab keeps the bar.
  try {
    const q = await getQueue();
    if (q && tab.openerTabId && q.tabs.includes(tab.openerTabId) && !q.tabs.includes(tab.id)) {
      q.tabs.push(tab.id);
      await setQueue(q);
    }
  } catch (e) { /* the queue is a convenience; never throw from here */ }
});
chrome.tabs.onRemoved.addListener(async (tabId) => {
  try {
    const q = await getQueue();
    if (q && q.tabs.includes(tabId)) { q.tabs = q.tabs.filter((t) => t !== tabId); await setQueue(q); }
  } catch (e) { /* ignore */ }
});

// ---- Forms inside iframes ----
// Some application systems (iCIMS, embedded Greenhouse) put the whole form in
// an iframe. The content script runs in every frame; each sub-frame announces
// itself here, and the top frame's sidebar asks for work to be done in them.
// The list lives in session storage so it survives the service worker sleeping.
async function frameList(tabId) {
  const all = (await chrome.storage.session.get("riseply_frames")).riseply_frames || {};
  return all[tabId] || [];
}
async function saveFrameList(tabId, ids) {
  const all = (await chrome.storage.session.get("riseply_frames")).riseply_frames || {};
  if (ids.length) all[tabId] = ids; else delete all[tabId];
  await chrome.storage.session.set({ riseply_frames: all });
}
function sendToFrame(tabId, frameId, op, args, timeoutMs) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve({ frameId, failed: true }), timeoutMs);
    try {
      chrome.tabs.sendMessage(tabId, { type: "RF_OP", op, args }, { frameId }, (result) => {
        clearTimeout(timer);
        if (chrome.runtime.lastError) { resolve({ frameId, failed: true }); return; }
        resolve({ frameId, result });
      });
    } catch (e) {
      clearTimeout(timer);
      resolve({ frameId, failed: true });
    }
  });
}
chrome.tabs.onRemoved.addListener((tabId) => { saveFrameList(tabId, []).catch(() => {}); });

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  log("received message:", message.type);
  (async () => {
    try {
      switch (message.type) {
        case "LOGIN": {
          const result = await apiFetch("/auth/login", {
            method: "POST",
            body: JSON.stringify({ email: message.email, password: message.password }),
          });
          await chrome.storage.local.set({ riseply_token: result.access_token });
          sendResponse({ success: true });
          break;
        }

        case "LOGOUT": {
          await chrome.storage.local.remove("riseply_token");
          sendResponse({ success: true });
          break;
        }

        case "GET_AUTH_STATE": {
          const token = await getToken();
          log("stored token present:", !!token);
          if (!token) {
            sendResponse({ loggedIn: false });
            break;
          }
          try {
            const me = await apiFetch("/me");
            sendResponse({ loggedIn: true, user: me });
          } catch (e) {
            log("GET_AUTH_STATE's /me call failed:", e.message || e);
            // Only a rejected login (401/403) means the token is dead. A
            // timeout, a server waking from idle or a dropped connection
            // says nothing about the login, so keep the token and say the
            // server could not be reached instead of logging the person out.
            if (e.status === 401 || e.status === 403) {
              await chrome.storage.local.remove("riseply_token");
              sendResponse({ loggedIn: false });
            } else {
              sendResponse({ loggedIn: false, unreachable: true, error: "Couldn't reach Riseply just now. The server may be waking up. Try again in a moment." });
            }
          }
          break;
        }

        case "SCORE_JOB": {
          const result = await apiFetch("/extension/score-job", {
            method: "POST",
            body: JSON.stringify({
              title: message.title, company: message.company,
              location: message.location || "", description: message.description,
            }),
          });
          sendResponse({ success: true, ...result });
          break;
        }

        case "ANSWER_QUESTION": {
          const result = await apiFetch("/extension/answer-question", {
            method: "POST",
            body: JSON.stringify({
              question: message.question, title: message.title,
              company: message.company, description: message.description,
              options: message.options || [],
            }),
          });
          sendResponse({ success: true, ...result });
          break;
        }

        case "GENERATE_COVER_LETTER": {
          const result = await apiFetch("/extension/generate-cover-letter", {
            method: "POST",
            body: JSON.stringify({
              title: message.title, company: message.company, description: message.description,
            }),
          });
          sendResponse({ success: true, ...result });
          break;
        }

        case "GET_CANDIDATE": {
          // Email and phone come from the default resume (what the recruiter sees);
          // the profile is the fallback, and also covers an older server without this route.
          let c = null;
          try { c = await apiFetch("/extension/candidate"); } catch (e) { /* fall back below */ }
          if (!c || !c.email) {
            const me = await apiFetch("/me");
            c = { ...(c || {}), full_name: me.full_name || "", email: me.email || "", email_source: "profile",
              phone: (c && c.phone) || me.phone || "", location: me.location || "",
              linkedin_url: me.linkedin_url || "", portfolio_url: me.portfolio_url || "" };
          }
          sendResponse({
            success: true,
            candidate: {
              full_name: c.full_name || "", email: c.email || "", email_source: c.email_source || "",
              phone: c.phone || "", location: c.location || "",
              linkedin_url: c.linkedin_url || "", portfolio_url: c.portfolio_url || "",
            },
          });
          break;
        }

        case "GET_AUTOFILL_PROFILE": {
          // Work history, education and the person's own saved answers.
          // A failure here must not break basic autofill, so the caller
          // treats any error as "no profile".
          const r = await apiFetch("/autofill-profile");
          sendResponse({ success: true, profile: r.profile });
          break;
        }

        // Site logins live only in this browser (chrome.storage.local) and are
        // never sent to Riseply. Keyed by site so a look-alike domain can't
        // receive them.
        case "GET_SITE_LOGIN": {
          const key = siteKey(message.host);
          const { riseply_logins } = await chrome.storage.local.get("riseply_logins");
          const c = (riseply_logins || {})[key];
          sendResponse({ success: true, site: key, login: c ? { username: c.username, password: c.password } : null });
          break;
        }

        case "SAVE_SITE_LOGIN": {
          const key = siteKey(message.host);
          const username = String(message.username || "").slice(0, 200);
          const password = String(message.password || "").slice(0, 200);
          if (!username || !password) {
            sendResponse({ success: false, error: "Enter both a username and a password." });
            break;
          }
          const { riseply_logins } = await chrome.storage.local.get("riseply_logins");
          await chrome.storage.local.set({ riseply_logins: { ...(riseply_logins || {}), [key]: { username, password } } });
          sendResponse({ success: true, site: key });
          break;
        }

        case "FORGET_SITE_LOGIN": {
          const key = siteKey(message.host);
          const { riseply_logins } = await chrome.storage.local.get("riseply_logins");
          const next = { ...(riseply_logins || {}) };
          delete next[key];
          await chrome.storage.local.set({ riseply_logins: next });
          sendResponse({ success: true });
          break;
        }

        case "JOB_STATUS": {
          const r = await apiFetch("/extension/job-status", { method: "POST", body: JSON.stringify({ url: message.url || "" }) });
          sendResponse({ success: true, ...r });
          break;
        }

        case "TAILOR_RESUME": {
          const r = await apiFetch("/extension/tailor", {
            method: "POST",
            body: JSON.stringify({
              title: message.title, company: message.company, location: message.location || "",
              description: message.description, url: message.url || "",
            }),
          });
          sendResponse({ success: true, ...r });
          break;
        }

        case "QUEUE_PEEK": {
          const q = await getQueue();
          const r = await apiFetch("/applications/apply-queue");
          sendResponse({ success: true, count: (r.items || []).length, appliedThisWeek: r.applied_this_week || 0,
            running: q ? { index: q.index, total: q.items.length } : null });
          break;
        }

        case "QUEUE_START": {
          const r = await apiFetch("/applications/apply-queue");
          const items = (r.items || []).filter((i) => safeUrl(i.url)).map((i) => ({
            id: i.id, title: i.title, company: i.company, url: i.url, score: i.match_score }));
          if (!items.length) { sendResponse({ success: true, count: 0 }); break; }
          const tab = await chrome.tabs.create({ url: items[0].url });
          await setQueue({ items, index: 0, tabs: [tab.id], applied: 0, skipped: 0 });
          sendResponse({ success: true, count: items.length });
          break;
        }

        case "QUEUE_RESUME": {
          const q = await getQueue();
          if (!q || !q.items[q.index]) { sendResponse({ success: false, error: "No queue is running." }); break; }
          const tab = await chrome.tabs.create({ url: safeUrl(q.items[q.index].url) });
          q.tabs = [tab.id];
          await setQueue(q);
          sendResponse({ success: true });
          break;
        }

        case "QUEUE_STATE": {
          const q = await getQueue();
          sendResponse(q ? queueView(q, _sender.tab && _sender.tab.id) : { success: true, active: false });
          break;
        }

        case "QUEUE_NEXT": {
          const q = await getQueue();
          const tabId = _sender.tab && _sender.tab.id;
          if (!q || !q.tabs.includes(tabId)) { sendResponse({ success: false, error: "No queue is running in this tab." }); break; }
          if (message.applied) q.applied += 1; else q.skipped += 1;
          q.index += 1;
          if (q.index >= q.items.length) {
            await setQueue(null);
            sendResponse({ success: true, done: true, applied: q.applied, skipped: q.skipped });
            break;
          }
          await openInQueueTab(q, q.items[q.index].url);
          await setQueue(q);
          sendResponse({ success: true, done: false });
          break;
        }

        case "QUEUE_STOP": {
          await setQueue(null);
          sendResponse({ success: true });
          break;
        }

        case "MARK_APPLIED": {
          const r = await apiFetch("/extension/applied", {
            method: "POST",
            body: JSON.stringify({ application_id: message.applicationId || null, url: message.url || "" }),
          });
          sendResponse({ success: true, ...r });
          break;
        }

        case "LOG_UNANSWERED": {
          // Only the text of the questions Autofill left for the person, and
          // the site's address. Never anything typed into the form.
          const r = await apiFetch("/extension/unanswered", {
            method: "POST",
            body: JSON.stringify({ questions: (message.questions || []).slice(0, 40), host: message.host || "" }),
          });
          sendResponse({ success: true, ...r });
          break;
        }

        case "GET_RESUME_FILE": {
          const f = await apiFetch("/extension/resume-file" + (message.applicationId ? `?application_id=${encodeURIComponent(message.applicationId)}` : ""));
          sendResponse({ success: true, ...f });
          break;
        }

        case "GET_USAGE": {
          const usage = await apiFetch("/usage");
          sendResponse({
            success: true,
            tier: usage.tier,
            matchesUsed: usage.matches_used,
            matchesLimit: usage.matches_limit,
          });
          break;
        }

        case "FRAME_HELLO": {
          const tabId = _sender.tab && _sender.tab.id;
          const frameId = _sender.frameId;
          if (tabId != null && frameId) {
            const ids = await frameList(tabId);
            if (!ids.includes(frameId)) { ids.push(frameId); await saveFrameList(tabId, ids.slice(-40)); }
          }
          sendResponse({ success: true });
          break;
        }

        case "FRAME_OP": {
          const tabId = _sender.tab && _sender.tab.id;
          if (tabId == null) { sendResponse({ success: true, results: [] }); break; }
          const known = await frameList(tabId);
          const targets = message.frameId != null ? [message.frameId] : known;
          const timeout = message.timeoutMs || 30000;
          const answers = await Promise.all(targets.map((id) => sendToFrame(tabId, id, message.op, message.args || {}, timeout)));
          const gone = answers.filter((a) => a.failed).map((a) => a.frameId);
          if (gone.length) await saveFrameList(tabId, known.filter((id) => !gone.includes(id)));
          sendResponse({ success: true, results: answers.filter((a) => !a.failed).map((a) => ({ frameId: a.frameId, result: a.result })) });
          break;
        }

        default:
          sendResponse({ success: false, error: "Unknown message type" });
      }
    } catch (err) {
      log("handler threw for", message.type, ":", err.message || err);
      sendResponse({ success: false, error: err.message || String(err), status: err.status });
    }
  })();

  return true; // keeps the message channel open for the async response above
});
