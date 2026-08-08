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
  if (!auth.loggedIn) {
    renderLoggedOut();
    return;
  }

  app.innerHTML = `
    <div class="status">
      <div class="name">${escapeHtml(auth.user.full_name || auth.user.email)}</div>
      <div class="email">${escapeHtml(auth.user.email)}</div>
      <button class="ghost" id="logout-btn">Log out</button>
    </div>
    <p class="hint">Open a job posting page (Greenhouse, Lever, or most company careers pages) to see the Riseply sidebar.</p>
  `;

  document.getElementById("logout-btn").addEventListener("click", async () => {
    await sendMessage({ type: "LOGOUT" });
    renderLoggedOut();
  });
}

(async function init() {
  const auth = await sendMessage({ type: "GET_AUTH_STATE" });
  if (auth.loggedIn) {
    renderLoggedIn();
  } else {
    renderLoggedOut();
  }
})();
