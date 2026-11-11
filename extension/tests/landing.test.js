// Run: node extension/tests/landing.test.js
// On a landing step ("Apply Manually"), Autofill points at the page's button and,
// once the person presses it, fills the form by itself when it appears.
const path = require("path");
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");
const assert = require("assert");
(async () => {
  const b = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const p = await b.newPage();
  await p.addInitScript(() => {
    window.chrome = { runtime: { id: "x", lastError: null, sendMessage(m, cb) {
      const ok = (o) => setTimeout(() => cb({ success: true, ...o }), 0);
      if (m.type === "GET_AUTH_STATE") return ok({ loggedIn: true, user: { email: "a@b.c" } });
      if (m.type === "JOB_STATUS") return ok({ in_list: false });
      if (m.type === "GET_CANDIDATE") return ok({ candidate: { full_name: "JANE DOE", email: "j@x.com", phone: "2025550123" } });
      if (m.type === "GET_AUTOFILL_PROFILE") return ok({ profile: { work: [], education: [], answers: {}, eeo: {}, saved_answers: [] } });
      return ok({});
    } } };
  });
  await p.goto("file://" + path.join(__dirname, "fixture_landing.html"));
  for (const f of ["jobdetect.js", "jobinfo.js", "profilefill.js", "content.js"]) await p.addScriptTag({ path: path.join(__dirname, "..", f) });
  const q = (sel) => p.locator("#riseply-sidebar-host " + sel);
  await q("#riseply-fill-btn").waitFor();
  await q("#riseply-fill-btn").click();
  await q("#riseply-gate-btn").waitFor();
  assert.match(await q("#riseply-filled-slot").innerText(), /no form on this step yet/i);
  assert.equal(await p.$("#fn"), null, "nothing is clicked for the person");
  await q("#riseply-gate-btn").click();
  await p.waitForFunction(() => document.getElementById("fn") && document.getElementById("fn").value === "Jane", null, { timeout: 15000 });
  assert.equal(await p.$eval("#em", (e) => e.value), "j@x.com");
  assert.equal(await p.$eval("#ph", (e) => e.value), "2025550123");
  await b.close();
  console.log("ok");
})();
