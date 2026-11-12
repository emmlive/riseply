// Run: node extension/tests/queue.test.js
// The Apply queue: background logic (which tab, what order, what is counted) and
// the on-page bar (what it offers, that it never submits for the person).
const path = require("path");
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");

const QUEUE_API = {
  applied_this_week: 2,
  items: [
    { id: 11, title: "Security Analyst", company: "Acme", url: "https://boards.greenhouse.io/acme/1", match_score: 92 },
    { id: 12, title: "GRC Engineer", company: "Beta", url: "https://www.linkedin.com/jobs/view/2", match_score: 88 },
    { id: 13, title: "Bad link", company: "Gamma", url: "javascript:alert(1)", match_score: 80 },
    { id: 14, title: "Auditor", company: "Delta", url: "https://jobs.lever.co/delta/4", match_score: 77 },
  ],
};

function loadBackground() {
  const store = {}; const local = { riseply_token: "tok" };
  const tabs = { created: [], updated: [], nextId: 100, missing: new Set() };
  const listeners = { message: null, created: [], removed: [] };
  const calls = [];
  const chrome = {
    runtime: { onMessage: { addListener: (f) => { listeners.message = f; } }, onInstalled: { addListener() {} } },
    storage: {
      local: { async get(k) { return { [k]: local[k] }; }, async set(o) { Object.assign(local, o); }, async remove(k) { delete local[k]; } },
      session: { async get(k) { return { [k]: store[k] }; }, async set(o) { Object.assign(store, o); }, async remove(k) { delete store[k]; } },
    },
    tabs: {
      async create({ url }) { const t = { id: tabs.nextId++, url }; tabs.created.push(t); return t; },
      async update(id, { url }) { if (tabs.missing.has(id)) throw new Error("No tab"); tabs.updated.push({ id, url }); return { id }; },
      onCreated: { addListener: (f) => listeners.created.push(f) }, onRemoved: { addListener: (f) => listeners.removed.push(f) },
    },
  };
  const fetch = async (url, opts) => {
    calls.push({ url, opts });
    const body = url.endsWith("/applications/apply-queue") ? QUEUE_API : url.endsWith("/extension/applied") ? { found: true } : {};
    return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => body };
  };
  const ctx = vm.createContext({ chrome, fetch, console: { log() {}, error() {}, warn() {} }, setTimeout, clearTimeout, URL });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "background.js"), "utf8"), ctx);
  const send = (message, tabId) => new Promise((resolve) => {
    listeners.message(message, { tab: tabId == null ? undefined : { id: tabId } }, resolve);
  });
  return { send, tabs, store, listeners, calls };
}

(async () => {
  // ---------- background ----------
  const bg = loadBackground();
  const peek = await bg.send({ type: "QUEUE_PEEK" });
  assert.equal(peek.count, 4); assert.equal(peek.running, null);

  const start = await bg.send({ type: "QUEUE_START" });
  assert.equal(start.count, 3, "a job with an unusable link is left out");
  assert.equal(bg.tabs.created[0].url, "https://boards.greenhouse.io/acme/1");
  const tab = bg.tabs.created[0].id;

  let st = await bg.send({ type: "QUEUE_STATE" }, tab);
  assert.equal(st.active, true); assert.equal(st.index, 0); assert.equal(st.total, 3); assert.equal(st.item.id, 11);
  assert.equal((await bg.send({ type: "QUEUE_STATE" }, 999)).active, false, "other tabs get no bar");

  // An Apply link that opens a new tab from the queue tab keeps the bar there too.
  for (const f of bg.listeners.created) await f({ id: 555, openerTabId: tab });
  assert.equal((await bg.send({ type: "QUEUE_STATE" }, 555)).active, true);
  for (const f of bg.listeners.created) await f({ id: 556, openerTabId: 12345 });
  assert.equal((await bg.send({ type: "QUEUE_STATE" }, 556)).active, false, "unrelated tabs don't join");

  let n = await bg.send({ type: "QUEUE_NEXT", applied: true }, tab);
  assert.equal(n.done, false);
  assert.deepEqual(bg.tabs.updated[0], { id: tab, url: "https://www.linkedin.com/jobs/view/2" });
  assert.equal((await bg.send({ type: "QUEUE_STATE" }, 555)).active, false, "extra tabs are dropped once we move on");

  n = await bg.send({ type: "QUEUE_NEXT", applied: false }, tab);
  assert.equal(n.done, false); assert.equal(bg.tabs.updated[1].url, "https://jobs.lever.co/delta/4");

  // The queue tab was closed: the next job opens in a fresh tab instead of failing.
  bg.tabs.missing.add(tab);
  st = await bg.send({ type: "QUEUE_STATE" }, tab);
  const resume = await bg.send({ type: "QUEUE_RESUME" });
  assert.equal(resume.success, true);
  const t2 = bg.tabs.created[bg.tabs.created.length - 1].id;
  n = await bg.send({ type: "QUEUE_NEXT", applied: true }, t2);
  assert.deepEqual([n.done, n.applied, n.skipped], [true, 2, 1]);
  assert.equal((await bg.send({ type: "QUEUE_STATE" }, t2)).active, false, "finished queue clears");

  // Starting with nothing to do, and stopping.
  const bg2 = loadBackground();
  await bg2.send({ type: "QUEUE_START" });
  const t = bg2.tabs.created[0].id;
  await bg2.send({ type: "QUEUE_STOP" });
  assert.equal((await bg2.send({ type: "QUEUE_STATE" }, t)).active, false);
  assert.equal((await bg2.send({ type: "QUEUE_NEXT", applied: true }, t)).success, false, "no queue, no advance");

  // ---------- the bar ----------
  const b = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const page = await b.newPage();
  await page.addInitScript(() => {
    window.__sent = [];
    window.chrome = { runtime: { id: "x", lastError: null, sendMessage(m, cb) {
      window.__sent.push(m);
      const ok = (o) => setTimeout(() => cb({ success: true, ...o }), 0);
      if (m.type === "QUEUE_STATE") return ok({ active: true, index: 1, total: 3, item: { id: 12, title: "GRC <b>Engineer</b>", company: "Beta" }, applied: 1, skipped: 0 });
      if (m.type === "QUEUE_NEXT") return ok({ done: window.__done === true, applied: 2, skipped: 1 });
      return ok({});
    } } };
  });
  await page.goto("file://" + path.join(__dirname, "fixture_single.html"));
  await page.addScriptTag({ path: path.join(__dirname, "..", "queuebar.js") });
  const bar = (sel) => page.locator("#riseply-queue-host " + sel);
  await bar("#q-done").waitFor();
  assert.match(await bar(".what").innerText(), /2 of 3/);
  assert.match(await bar(".what").innerText(), /GRC <b>Engineer<\/b> at Beta/, "job text is shown as text, never as markup");

  // Autofill with no sidebar says what to do instead of failing silently.
  await bar("#q-fill").click();
  assert.match(await bar(".msg").innerText(), /Open the application form first/);
  // With the sidebar's button present, it presses it like the person would.
  await page.evaluate(() => {
    const h = document.createElement("div"); h.id = "riseply-sidebar-host"; document.body.appendChild(h);
    const r = h.attachShadow({ mode: "open" }); r.innerHTML = '<button id="riseply-fill-btn">Autofill this page</button>';
    r.getElementById("riseply-fill-btn").addEventListener("click", () => { window.__filled = true; });
  });
  await bar("#q-fill").click();
  assert.equal(await page.evaluate(() => window.__filled), true);

  // "Applied, next job": marks THIS application, then asks for the next one. Nothing is submitted.
  await bar("#q-done").click();
  await page.waitForFunction(() => window.__sent.some((m) => m.type === "QUEUE_NEXT"));
  const sent = await page.evaluate(() => window.__sent);
  const mark = sent.find((m) => m.type === "MARK_APPLIED");
  assert.equal(mark.applicationId, 12);
  assert.ok(sent.findIndex((m) => m.type === "MARK_APPLIED") < sent.findIndex((m) => m.type === "QUEUE_NEXT"), "marked before moving on");
  assert.deepEqual(sent.find((m) => m.type === "QUEUE_NEXT").applied, true);

  // Skip does not mark anything. (After "next" the real tab navigates; here a reload stands in.)
  await page.reload();
  await page.addScriptTag({ path: path.join(__dirname, "..", "queuebar.js") });
  await bar("#q-skip").waitFor();
  await bar("#q-skip").click();
  await page.waitForFunction(() => window.__sent.some((m) => m.type === "QUEUE_NEXT"));
  const afterSkip = await page.evaluate(() => window.__sent.map((m) => m.type));
  assert.ok(!afterSkip.includes("MARK_APPLIED") && afterSkip.includes("QUEUE_NEXT"));

  // The last job: a finished summary appears (a fresh page: after "next" the tab normally navigates away).
  const p4 = await b.newPage();
  await p4.addInitScript(() => {
    window.chrome = { runtime: { id: "x", lastError: null, sendMessage(m, cb) {
      if (m.type === "QUEUE_STATE") return setTimeout(() => cb({ success: true, active: true, index: 2, total: 3, item: { id: 9, title: "Last", company: "Z" } }), 0);
      if (m.type === "QUEUE_NEXT") return setTimeout(() => cb({ success: true, done: true, applied: 2, skipped: 1 }), 0);
      setTimeout(() => cb({ success: true }), 0);
    } } };
  });
  await p4.goto("file://" + path.join(__dirname, "fixture_single.html"));
  await p4.addScriptTag({ path: path.join(__dirname, "..", "queuebar.js") });
  await p4.locator("#riseply-queue-host #q-skip").click();
  await p4.locator("#riseply-queue-host #q-close").waitFor();
  assert.match(await p4.locator("#riseply-queue-host .what").innerText(), /2 applied, 1 skipped/);
  await p4.locator("#riseply-queue-host #q-close").click();
  assert.equal(await p4.$("#riseply-queue-host"), null);

  // A failed "mark applied" keeps the person on the job instead of silently moving on.
  const p2 = await b.newPage();
  await p2.addInitScript(() => {
    window.__sent = [];
    window.chrome = { runtime: { id: "x", lastError: null, sendMessage(m, cb) {
      window.__sent.push(m);
      if (m.type === "QUEUE_STATE") return setTimeout(() => cb({ success: true, active: true, index: 0, total: 2, item: { id: 5, title: "T", company: "C" } }), 0);
      if (m.type === "MARK_APPLIED") return setTimeout(() => cb({ success: false, error: "offline" }), 0);
      setTimeout(() => cb({ success: true }), 0);
    } } };
  });
  await p2.goto("file://" + path.join(__dirname, "fixture_single.html"));
  await p2.addScriptTag({ path: path.join(__dirname, "..", "queuebar.js") });
  await p2.locator("#riseply-queue-host #q-done").click();
  await p2.locator("#riseply-queue-host .msg").waitFor();
  assert.match(await p2.locator("#riseply-queue-host .msg").innerText(), /Couldn't mark it applied/);
  assert.ok(!(await p2.evaluate(() => window.__sent)).some((m) => m.type === "QUEUE_NEXT"), "does not advance when marking failed");

  // No queue in this tab: no bar.
  const p3 = await b.newPage();
  await p3.addInitScript(() => { window.chrome = { runtime: { id: "x", lastError: null, sendMessage(m, cb) { setTimeout(() => cb({ success: true, active: false }), 0); } } }; });
  await p3.goto("file://" + path.join(__dirname, "fixture_single.html"));
  await p3.addScriptTag({ path: path.join(__dirname, "..", "queuebar.js") });
  await p3.waitForTimeout(300);
  assert.equal(await p3.$("#riseply-queue-host"), null);

  // In the queue's tab the sidebar shows even on a page the job detector wouldn't pick; elsewhere it stays away.
  for (const active of [true, false]) {
    const pg = await b.newPage();
    await pg.addInitScript((isActive) => {
      window.chrome = { runtime: { id: "x", lastError: null, sendMessage(m, cb) {
        const ok = (o) => setTimeout(() => cb({ success: true, ...o }), 0);
        if (m.type === "QUEUE_STATE") return ok(isActive ? { active: true, index: 0, total: 1, item: { id: 1, title: "T", company: "C" } } : { active: false });
        if (m.type === "GET_AUTH_STATE") return ok({ loggedIn: true, user: { email: "a@b.c" } });
        return ok({});
      } } };
    }, active);
    await pg.goto("data:text/html,<html><body><h1>Some page</h1><p>Weather and recipes.</p></body></html>");
    for (const f of ["jobdetect.js", "jobinfo.js", "profilefill.js", "content.js"]) await pg.addScriptTag({ path: path.join(__dirname, "..", f) });
    await pg.waitForTimeout(800);
    assert.equal(!!(await pg.$("#riseply-sidebar-host")), active, active ? "queue tab gets the sidebar" : "other pages stay clean");
  }

  await b.close();
  console.log("ok");
})().catch((e) => { console.error(e); process.exit(1); });
