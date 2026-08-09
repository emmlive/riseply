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

function log(...args) {
  console.log("[Riseply:bg]", ...args);
}

async function getToken() {
  const { riseply_token } = await chrome.storage.local.get("riseply_token");
  return riseply_token || null;
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
    const error = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    error.status = res.status;
    throw error;
  }
  return body;
}

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
            // Token expired/invalid -- clear it so the popup shows the
            // login form again instead of a silently-failing "logged in"
            // state that can never actually complete a request.
            log("GET_AUTH_STATE's /me call failed:", e.message || e);
            await chrome.storage.local.remove("riseply_token");
            sendResponse({ loggedIn: false });
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

        case "GET_CANDIDATE": {
          const me = await apiFetch("/me");
          sendResponse({
            success: true,
            candidate: {
              full_name: me.full_name || "", email: me.email || "",
              phone: me.phone || "", location: me.location || "",
              linkedin_url: me.linkedin_url || "", portfolio_url: me.portfolio_url || "",
            },
          });
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
