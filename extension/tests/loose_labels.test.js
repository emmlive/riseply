// Run: node extension/tests/loose_labels.test.js
// Application forms whose labels are not tied to the boxes (a <div> above the input,
// random ids and names) still get the name, email and phone filled.
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
  await p.goto("file://" + path.join(__dirname, "fixture_loose_labels.html"));
  for (const f of ["jobdetect.js", "jobinfo.js", "profilefill.js", "content.js"]) await p.addScriptTag({ path: path.join(__dirname, "..", f) });
  await p.locator("#riseply-sidebar-host #riseply-fill-btn").waitFor();
  await p.locator("#riseply-sidebar-host #riseply-fill-btn").click();
  await p.waitForFunction(() => document.getElementById("in-a1").value !== "");
  const v = (id) => p.$eval("#" + id, (e) => e.value);
  assert.equal(await v("in-a1"), "Jane");
  assert.equal(await v("in-a2"), "Doe");
  assert.equal(await v("in-a3"), "j@x.com");
  assert.equal(await v("in-a4"), "2025550123");
  assert.equal(await v("in-a5"), "", "an unrelated box is left alone");
  await b.close();
  console.log("ok");
})();
