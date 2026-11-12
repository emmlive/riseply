// Riseply Autofill -- the "next job" bar.
//
// When the person starts the Apply queue from the toolbar popup, the job opens
// in a tab and this slim bar rides along on every page of that tab: Autofill,
// "Applied, next job" and Skip. It never clicks the employer's Submit button
// and never marks anything applied on its own. Top frame only.
(function () {
  if (window !== window.top) return;
  if (/(^|\.)riseply\.(com|onrender\.com)$/.test(location.hostname)) return;

  const HOST_ID = "riseply-queue-host";

  function send(message) {
    return new Promise((resolve) => {
      try {
        if (!chrome.runtime || !chrome.runtime.id) { resolve({ success: false }); return; }
        chrome.runtime.sendMessage(message, (r) => {
          resolve(chrome.runtime.lastError || !r ? { success: false } : r);
        });
      } catch (e) { resolve({ success: false }); }
    });
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  const CSS = `
    :host { all: initial; }
    .bar { font: 13px/1.3 -apple-system, 'Inter', 'Segoe UI', sans-serif; color: #fff; background: #16233D;
      border-radius: 12px; box-shadow: 0 6px 24px rgba(0,0,0,.28); padding: 10px 12px; display: flex; gap: 10px;
      align-items: center; flex-wrap: wrap; max-width: min(760px, calc(100vw - 24px)); }
    .what { flex: 1 1 220px; min-width: 0; }
    .what b { display: block; font-size: 12px; color: #9FD9CD; font-weight: 600; }
    .what span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    button { font: inherit; font-weight: 600; border: 0; border-radius: 8px; padding: 8px 12px; cursor: pointer; }
    button:disabled { opacity: .55; cursor: default; }
    .go { background: #1F7A6C; color: #fff; }
    .go:hover:not(:disabled) { background: #17604F; }
    .alt { background: #E4F0EC; color: #17604F; }
    .quiet { background: transparent; color: #C9D3E6; padding: 8px 6px; font-weight: 500; }
    .msg { flex-basis: 100%; font-size: 12px; color: #FFD9A8; margin: 0; }
  `;

  let root = null;
  let state = null;
  let busy = false;
  let message = "";

  function ensureHost() {
    let host = document.getElementById(HOST_ID);
    if (!host) {
      host = document.createElement("div");
      host.id = HOST_ID;
      host.style.cssText = "position:fixed;bottom:16px;left:50%;transform:translateX(-50%);z-index:2147483647;";
      document.documentElement.appendChild(host);
      root = host.attachShadow({ mode: "open" });
    } else if (!root) {
      root = host.shadowRoot;
    }
    return root;
  }

  function draw(finished) {
    const r = ensureHost();
    if (finished) {
      r.innerHTML = `<style>${CSS}</style><div class="bar"><div class="what"><b>Riseply queue finished</b>
        <span>${finished.applied} applied, ${finished.skipped} skipped.</span></div>
        <button class="alt" id="q-close">Close</button></div>`;
      r.getElementById("q-close").addEventListener("click", () => { const h = document.getElementById(HOST_ID); if (h) h.remove(); });
      return;
    }
    const it = state.item;
    r.innerHTML = `<style>${CSS}</style>
      <div class="bar">
        <div class="what"><b>Riseply queue · ${state.index + 1} of ${state.total}</b>
          <span>${esc(it.title)}${it.company ? " at " + esc(it.company) : ""}</span></div>
        <button class="alt" id="q-fill" ${busy ? "disabled" : ""}>Autofill this page</button>
        <button class="go" id="q-done" ${busy ? "disabled" : ""}>Applied, next job</button>
        <button class="quiet" id="q-skip" ${busy ? "disabled" : ""}>Skip</button>
        <button class="quiet" id="q-stop" ${busy ? "disabled" : ""}>Stop</button>
        ${message ? `<p class="msg" role="status">${esc(message)}</p>` : ""}
      </div>`;
    r.getElementById("q-fill").addEventListener("click", autofill);
    r.getElementById("q-done").addEventListener("click", () => advance(true));
    r.getElementById("q-skip").addEventListener("click", () => advance(false));
    r.getElementById("q-stop").addEventListener("click", stop);
  }

  function autofill() {
    // The sidebar owns Autofill. Press its button the same way the person would.
    const side = document.getElementById("riseply-sidebar-host");
    const btn = side && side.shadowRoot && side.shadowRoot.getElementById("riseply-fill-btn");
    if (!btn) {
      message = "Open the application form first, then press Autofill again.";
      draw();
      return;
    }
    message = "";
    btn.click();
    draw();
  }

  async function advance(applied) {
    if (busy) return;
    busy = true; message = ""; draw();
    if (applied) {
      const r = await send({ type: "MARK_APPLIED", applicationId: state.item.id, url: location.href });
      if (!r.success) {
        // Say so and stop here: the person decides whether to retry or skip.
        busy = false;
        message = "Couldn't mark it applied on Riseply. Try again, or press Skip.";
        draw();
        return;
      }
    }
    const next = await send({ type: "QUEUE_NEXT", applied });
    busy = false;
    if (!next.success) { message = "Couldn't open the next job. Try again."; draw(); return; }
    if (next.done) draw({ applied: next.applied, skipped: next.skipped });
    // Otherwise the tab is navigating to the next job and this bar will be rebuilt there.
  }

  async function stop() {
    await send({ type: "QUEUE_STOP" });
    const h = document.getElementById(HOST_ID);
    if (h) h.remove();
  }

  async function boot() {
    const st = await send({ type: "QUEUE_STATE" });
    if (!st.success || !st.active || !st.item) return;
    state = st;
    window.__risePlyQueue = true;
    draw();
  }

  if (document.readyState === "complete" || document.readyState === "interactive") boot();
  else document.addEventListener("DOMContentLoaded", boot);
})();
