// Run: node extension/tests/workday_info.test.js
// Real Workday mistakes seen on a live application, each kept from coming back.
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
      if (m.type === "GET_CANDIDATE") return ok({ candidate: { full_name: "JANE DOE", email: "j@x.com", phone: "2025550123", location: "Plainfield, IL" } });
      if (m.type === "GET_AUTOFILL_PROFILE") return ok({ profile: { work: [{ company: "Acme", title: "IT Auditor", start: "Nov 2024", end: "", current: false, summary: "" }], education: [], answers: {}, eeo: {}, saved_answers: [] } });
      return ok({});
    } } };
  });
  await p.goto("file://" + path.join(__dirname, "fixture_workday_info.html"));
  for (const f of ["jobdetect.js", "jobinfo.js", "profilefill.js", "content.js"]) await p.addScriptTag({ path: path.join(__dirname, "..", f) });
  await p.locator("#riseply-sidebar-host #riseply-fill-btn").waitFor();
  await p.locator("#riseply-sidebar-host #riseply-fill-btn").click();
  await p.waitForFunction(() => document.getElementById("pn").value !== "", null, { timeout: 15000 });
  const v = (id) => p.$eval("#" + id, (e) => e.value);
  assert.equal(await v("pn"), "2025550123", "phone goes in the Phone Number box");
  assert.equal(await p.$eval("#pdt", (e) => e.textContent), "Select One", "the device type button is not typed into");
  assert.equal(await v("px"), "", "extension is left alone");
  assert.notEqual(await v("co"), "Jane Doe", "the person's name never goes in Company");
  assert.equal(await v("lo"), "", "home location is not written into a past job's location");
  await p.waitForFunction(() => document.getElementById("sdy").value !== "", null, { timeout: 15000 });
  const now = new Date();
  assert.equal(await v("sdy"), String(now.getFullYear()));
  assert.equal(await v("sd"), String(now.getMonth() + 1).padStart(2, "0"));
  assert.equal(await v("nm"), "Jane Doe");
  assert.equal(await v("jt"), "IT Auditor");
  assert.equal(await v("co"), "Acme", "company comes from work history");
  assert.equal(await v("fm"), "11"); assert.equal(await v("fy"), "2024", "From date is split into month and year boxes");
  await b.close();
  console.log("ok");
})();
