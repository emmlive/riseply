function sendMessage(message) {
  return new Promise((resolve) => chrome.runtime.sendMessage(message, resolve));
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

async function renderLoggedOut(error) {
  const app = document.getElementById("app");
  app.innerHTML = `
    <label for="email">Email</label>
    <input type="email" id="email" autocomplete="username" />
    <label for="password">Password</label>
    <input type="password" id="password" autocomplete="current-password" />
    <button class="primary" id="login-btn">Log in</button>
    ${error ? `<p class="error">${escapeHtml(error)}</p>` : ""}
    <p class="hint">Once logged in, open any job posting page and Riseply's sidebar will show your match score and an autofill button.</p>
  `;

  document.getElementById("login-btn").addEventListener("click", async () => {
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    const btn = document.getElementById("login-btn");
    if (!email || !password) return;

    btn.disabled = true;
    btn.textContent = "Logging in…";
    const result = await sendMessage({ type: "LOGIN", email, password });
    if (result.success) {
      await renderLoggedIn();
    } else {
      renderLoggedOut(result.error || "Couldn't log in — check your email and password.");
    }
  });

  // Enter key submits, same as clicking the button
  document.getElementById("password").addEventListener("keydown", (e) => {
    if (e.key === "Enter") document.getElementById("login-btn").click();
  });
}

async function renderLoggedIn() {
  const app = document.getElementById("app");
  app.innerHTML = `<p class="hint">Loading…</p>`;

  const auth = await sendMessage({ type: "GET_AUTH_STATE" });
  if (auth.unreachable) { renderUnreachable(auth.error); return; }
  if (!auth.loggedIn) {
    renderLoggedOut();
    return;
  }

  const usage = await sendMessage({ type: "GET_USAGE" });
  const usageHtml = usage.success
    ? `<p class="hint" style="margin-top:0;">
         ${usage.matchesUsed}/${usage.matchesLimit} matches used this month (${usage.tier === "pro" ? "Pro" : "Free"})
         ${usage.tier !== "pro" ? ' · <a href="https://riseply.com/dashboard/billing" target="_blank" style="color:inherit;">Upgrade</a>' : ""}
       </p>`
    : "";

  app.innerHTML = `
    <div class="status">
      <div class="name">${escapeHtml(auth.user.full_name || auth.user.email)}</div>
      <div class="email">${escapeHtml(auth.user.email)}</div>
      ${usageHtml}
      <button class="ghost" id="logout-btn">Log out</button>
    </div>
    <div id="queue-slot"></div>
    <p class="hint">Open a job posting page (Greenhouse, Lever, or most company careers pages) to see the Riseply sidebar. This shared match count also covers "Find new matches" on riseply.com -- scoring a job here uses the same monthly quota.</p>
  `;

  document.getElementById("logout-btn").addEventListener("click", async () => {
    await sendMessage({ type: "LOGOUT" });
    renderLoggedOut();
  });

  renderQueue();
}

// The Apply queue: best matches opened one at a time, with a bar on each page.
async function renderQueue() {
  const slot = document.getElementById("queue-slot");
  if (!slot) return;
  const peek = await sendMessage({ type: "QUEUE_PEEK" });
  if (!peek || !peek.success) return;   // non-critical: skip rather than show an error here
  if (peek.running) {
    slot.innerHTML = `
      <p class="hint" style="margin-top:0;">Queue running: job ${peek.running.index + 1} of ${peek.running.total}.</p>
      <button class="primary" id="queue-resume">Open the current job</button>
      <button class="ghost" id="queue-stop">Stop the queue</button>`;
    document.getElementById("queue-resume").addEventListener("click", async () => {
      await sendMessage({ type: "QUEUE_RESUME" });
      window.close();
    });
    document.getElementById("queue-stop").addEventListener("click", async () => {
      await sendMessage({ type: "QUEUE_STOP" });
      renderQueue();
    });
    return;
  }
  if (peek.count > 0) {
    slot.innerHTML = `
      <button class="primary" id="queue-start">Apply to my best matches (${peek.count})</button>
      <p class="hint">Opens them one at a time with a bar to autofill, mark applied and move on. You click each Submit.</p>`;
    document.getElementById("queue-start").addEventListener("click", async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Opening…";
      const r = await sendMessage({ type: "QUEUE_START" });
      if (r && r.success && r.count > 0) window.close();
      else renderQueue();
    });
    return;
  }
  slot.innerHTML = `<p class="hint" style="margin-top:0;">Your Apply queue is empty. Strong matches show up here as Riseply finds them.</p>`;
}

function renderUnreachable(message) {
  const app = document.getElementById("app");
  app.innerHTML = `
    <p class="error">${escapeHtml(message || "Couldn't reach Riseply just now.")}</p>
    <p class="hint">You are still logged in. Riseply's server can take up to a minute to wake up after being idle.</p>
    <button class="primary" id="retry-btn">Try again</button>
  `;
  document.getElementById("retry-btn").addEventListener("click", () => renderLoggedIn());
}

(async function init() {
  const auth = await sendMessage({ type: "GET_AUTH_STATE" });
  if (auth.unreachable) {
    renderUnreachable(auth.error);
  } else if (auth.loggedIn) {
    renderLoggedIn();
  } else {
    renderLoggedOut();
  }
})();
