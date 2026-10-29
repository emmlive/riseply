// Run: node extension/tests/profilefill.test.js  (needs playwright and a chromium)
const path = require("path");
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");
const assert = require("assert");

const profile = {
  work: [
    { company: "Acme", title: "IT Auditor", start: "Jan 2019", end: "", current: true, summary: "Led SOX testing." },
    { company: "Globex", title: "Analyst", start: "Mar 2016", end: "Dec 2018", current: false, summary: "" },
  ],
  education: [{ school: "Missouri State University", degree: "M.S.", field: "Cybersecurity", start: "2020", end: "2022" }],
  answers: { work_authorized_us: "yes", needs_sponsorship: "no", willing_to_relocate: "", salary_expectation: "$150,000", notice_period: "Two weeks", earliest_start_date: "" },
  eeo: { gender: "Decline to answer", race: "Asian", veteran: "No", disability: "" },
  saved_answers: [{ question: "Why do you want to work at this company?", answer: "I like the mission." }],
};

(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const p = await b.newPage();
  await p.goto("file://" + path.join(__dirname, "fixture.html"));
  await p.addScriptTag({ path: path.join(__dirname, "..", "profilefill.js") });
  const res = await p.evaluate((pr) => window.RisePlyFill.run(pr), profile);
  const v = (sel) => p.$eval(sel, (e) => e.value);
  const sel = (sel) => p.$eval(sel, (e) => e.selectedOptions[0].text);

  assert.equal(await sel("#a"), "Yes");
  assert.equal(await p.$eval('input[name=sp][value=n]', (e) => e.checked), true);
  assert.equal(await p.$eval('input[name=sp][value=y]', (e) => e.checked), false);
  assert.equal(await v("#rl"), "", "blank answer must be left alone");
  assert.equal(await v("#sal"), "$150,000");
  assert.equal(await v("#np"), "Two weeks");
  assert.equal(await v("#why"), "I like the mission.");
  assert.equal(await v("#other"), "", "unrelated question must not get a saved answer");
  assert.deepEqual(await p.$$eval(".jt", (e) => e.map((x) => x.value)), ["IT Auditor", "Analyst"]);
  assert.deepEqual(await p.$$eval(".jc", (e) => e.map((x) => x.value)), ["Acme", "Globex"]);
  assert.deepEqual(await p.$$eval(".js", (e) => e.map((x) => x.value)), ["01/2019", "03/2016"]);
  assert.deepEqual(await p.$$eval(".je", (e) => e.map((x) => x.value)), ["", "12/2018"], "current job has no end date");
  assert.equal(await v("#sc"), "Missouri State University");
  assert.equal(await v("#fs"), "Cybersecurity");
  assert.equal(await v("#es"), "2020");
  assert.equal(await v("#ee"), "2022");
  assert.equal(await sel("#g"), "Decline to self-identify");
  assert.equal(await sel("#r"), "Asian (Not Hispanic or Latino)");
  assert.equal(await sel("#v"), "I am not a protected veteran");
  assert.equal(await sel("#d"), "Select", "blank self-identification must stay unanswered");

  // Pressing it again must change nothing that is already filled.
  await p.fill(".jt", "Edited by hand");
  const again = await p.evaluate((pr) => window.RisePlyFill.run(pr), profile);
  assert.equal(await p.$eval(".jt", (e) => e.value), "Edited by hand");
  assert.equal(again.filled.length, 0, "second run fills nothing new");

  // An empty profile fills nothing.
  await p.reload();
  await p.addScriptTag({ path: path.join(__dirname, "..", "profilefill.js") });
  const none = await p.evaluate(() => window.RisePlyFill.run({ work: [], education: [], answers: {}, eeo: {}, saved_answers: [] }));
  assert.equal(none.filled.length, 0);
  assert.equal(await p.evaluate(() => window.RisePlyFill.isEmptyProfile({ answers: {}, eeo: {}, work: [], education: [], saved_answers: [] })), true);

  console.log("ok:", res.filled.join(", "));
  await b.close();
})().catch((e) => { console.error("FAIL", e.message); process.exit(1); });

// ---- job info reading (second suite) ----
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const p = await b.newPage();
  const read = async (file) => {
    await p.goto("file://" + path.join(__dirname, file));
    await p.addScriptTag({ path: path.join(__dirname, "..", "jobinfo.js") });
    return p.evaluate(() => window.RisePlyJob.read());
  };
  const a = await read("jobinfo.html");
  assert.equal(a.title, "Associate Partner - AI Integration", "skips the logo and banner headings");
  assert.equal(a.company, "IBM");
  const c = await read("jobinfo_ld.html");
  assert.equal(c.title, "Senior IT Auditor");
  assert.equal(c.company, "Globex");
  assert.equal(c.location, "Chicago, IL, US");
  console.log("ok: job info");
  await b.close();
})().catch((e) => { console.error("FAIL jobinfo", e.message); process.exit(1); });

// ---- resume attach (third suite) ----
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const p = await b.newPage();
  const payload = { filename: "Jane_Resume.pdf", content_type: "application/pdf", data: Buffer.from("%PDF-1.4 test").toString("base64") };
  const run = async (file) => {
    await p.goto("file://" + path.join(__dirname, file));
    await p.addScriptTag({ path: path.join(__dirname, "..", "profilefill.js") });
    return p.evaluate((pl) => window.RisePlyFill.attachResume(pl), payload);
  };
  const names = (sel) => p.$eval(sel, (e) => Array.from(e.files).map((f) => f.name + ":" + f.size));
  assert.equal(await run("fixture_upload.html"), true);
  assert.deepEqual(await names("#r"), ["Jane_Resume.pdf:13"], "resume field gets the file");
  assert.deepEqual(await names("#c"), [], "cover letter field is left alone");
  assert.equal(await p.evaluate((pl) => window.RisePlyFill.attachResume(pl), payload), false, "second run attaches nothing");
  assert.equal(await run("fixture_single.html"), true);
  assert.deepEqual(await names("#only"), ["Jane_Resume.pdf:13"], "a lone unlabeled upload field gets it");
  assert.equal(await run("fixture_two.html"), false, "transcript and writing sample are not resumes");
  console.log("ok: attach resume");
  await b.close();
})().catch((e) => { console.error("FAIL attach", e.message); process.exit(1); });

// ---- site login and next (fourth suite) ----
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const p = await b.newPage();
  const load = async (file) => {
    await p.goto("file://" + path.join(__dirname, file));
    await p.addScriptTag({ path: path.join(__dirname, "..", "profilefill.js") });
  };
  await load("fixture_login.html");
  assert.equal(await p.evaluate(() => window.RisePlyFill.hasLogin()), true);
  await p.fill("#u", "typed-by-hand");
  const r1 = await p.evaluate(() => window.RisePlyFill.fillLogin({ username: "me@x.com", password: "pw123" }));
  assert.deepEqual(r1, ["password"], "a username already typed is left alone");
  assert.equal(await p.$eval("#p", (e) => e.value), "pw123");
  assert.equal(await p.$eval("#u", (e) => e.value), "typed-by-hand");
  assert.equal(await p.evaluate(() => window.RisePlyFill.findAdvance().el.id), "go", "login button found");
  assert.equal(await p.evaluate(() => window.RisePlyFill.findAdvance().label), "log in");
  await load("fixture_login.html");
  assert.deepEqual(await p.evaluate(() => window.RisePlyFill.fillLogin({ username: "me@x.com", password: "pw123" })), ["username", "password"]);
  assert.equal(await p.$eval("#u", (e) => e.value), "me@x.com");
  await load("fixture_signup.html");
  assert.equal(await p.evaluate(() => window.RisePlyFill.hasLogin()), false, "sign-up forms are not login forms");
  assert.deepEqual(await p.evaluate(() => window.RisePlyFill.fillLogin({ username: "a", password: "b" })), []);
  assert.equal(await p.$eval("#p1", (e) => e.value), "");
  await load("fixture_next.html");
  assert.equal(await p.evaluate(() => window.RisePlyFill.findAdvance().el.id), "nx", "Next, never Submit or Back");
  console.log("ok: site login and next");
  await b.close();
})().catch((e) => { console.error("FAIL login", e.message); process.exit(1); });

// ---- sidebar: saving a site login and the Log in / Next confirm (fifth suite) ----
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const p = await b.newPage();
  await p.addInitScript(() => {
    const store = {};
    const siteKey = (h) => h.split(".").slice(-2).join(".");
    window.chrome = { runtime: { id: "x", lastError: null, sendMessage(m, cb) {
      const ok = (o) => setTimeout(() => cb({ success: true, ...o }), 0);
      if (m.type === "GET_AUTH_STATE") return ok({ loggedIn: true, user: { email: "a@b.c" } });
      if (m.type === "GET_USAGE") return ok({ tier: "pro", matchesUsed: 0, matchesLimit: 300 });
      if (m.type === "GET_SITE_LOGIN") return ok({ site: siteKey(m.host), login: store[siteKey(m.host)] || null });
      if (m.type === "SAVE_SITE_LOGIN") { store[siteKey(m.host)] = { username: m.username, password: m.password }; window.__saved = m; return ok({ site: siteKey(m.host) }); }
      if (m.type === "FORGET_SITE_LOGIN") { delete store[siteKey(m.host)]; return ok({}); }
      return ok({});
    } } };
  });
  await p.goto("file://" + path.join(__dirname, "fixture_sidebar_login.html"));
  for (const f of ["jobdetect.js", "jobinfo.js", "profilefill.js", "content.js"]) await p.addScriptTag({ path: path.join(__dirname, "..", f) });
  const q = (sel) => p.locator("#riseply-sidebar-host " + sel);
  await q("#riseply-login-user").waitFor();
  await q("#riseply-login-user").fill("me@x.com");
  await q("#riseply-login-pass").fill("s3cret");
  await q("#riseply-login-save").click();
  await q("#riseply-login-fill").waitFor();
  await q("#riseply-login-fill").click();
  await p.waitForFunction(() => document.getElementById("p").value === "s3cret");
  assert.equal(await p.$eval("#u", (e) => e.value), "me@x.com");
  await q("#riseply-next-btn").click();
  assert.equal(await p.evaluate(() => window.__clicked || 0), 0, "nothing is clicked before the confirm");
  await q("#riseply-next-yes").click();
  assert.equal(await p.evaluate(() => window.__clicked), 1, "confirm clicks the site's own Log in button once");
  console.log("ok: sidebar login and next");
  await b.close();
})().catch((e) => { console.error("FAIL sidebar", e.message); process.exit(1); });

// ---- sidebar: ATS resume, attach it, mark applied (sixth suite) ----
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const p = await b.newPage();
  const pdf = (t) => Buffer.from("%PDF-1.4 " + t).toString("base64");
  await p.addInitScript((pdfs) => {
    window.__calls = [];
    window.chrome = { runtime: { id: "x", lastError: null, sendMessage(m, cb) {
      window.__calls.push(m);
      const ok = (o) => setTimeout(() => cb({ success: true, ...o }), 0);
      if (m.type === "GET_AUTH_STATE") return ok({ loggedIn: true, user: { email: "a@b.c" } });
      if (m.type === "JOB_STATUS") return ok({ in_list: false });
      if (m.type === "TAILOR_RESUME") return ok({ in_list: true, application_id: 7, has_tailored: true, applied: false, created: true,
        rationale: "Led with SOX work.", ats: [{ label: "Length", ok: false, detail: "Too long." }, { label: "Plain layout", ok: true, detail: "" }] });
      if (m.type === "GET_RESUME_FILE") return ok(m.applicationId
        ? { filename: "tailored.pdf", content_type: "application/pdf", data: pdfs.t }
        : { filename: "base.pdf", content_type: "application/pdf", data: pdfs.b });
      if (m.type === "MARK_APPLIED") return ok({ found: true, already: false, status: "submitted" });
      if (m.type === "GET_CANDIDATE") return ok({ candidate: { full_name: "JANE DOE", email: "j@x.com" } });
      if (m.type === "GET_AUTOFILL_PROFILE") return ok({ profile: { work: [], education: [], answers: {}, eeo: {}, saved_answers: [] } });
      return ok({});
    } } };
  }, { t: pdf("tailored"), b: pdf("base") });
  await p.goto("file://" + path.join(__dirname, "fixture_sidebar_apply.html"));
  for (const f of ["jobdetect.js", "jobinfo.js", "profilefill.js", "content.js"]) await p.addScriptTag({ path: path.join(__dirname, "..", f) });
  const q = (sel) => p.locator("#riseply-sidebar-host " + sel);
  const fileName = () => p.$eval("#r", (e) => Array.from(e.files).map((f) => f.name).join(","));

  await q("#riseply-tailor-btn").waitFor();
  assert.equal(await q("#riseply-applied-btn").count(), 0, "nothing to mark for a job that is not in the list");
  await q("#riseply-tailor-btn").click();
  await q("#riseply-attach-btn").waitFor();
  assert.match(await q("#riseply-tailor-slot").innerText(), /ATS checks: 1 of 2 passed\. Too long\./);
  const sent = await p.evaluate(() => window.__calls.find((c) => c.type === "TAILOR_RESUME"));
  assert.ok(sent.title && sent.description.length > 80 && sent.url.startsWith("file://"));

  // base resume goes in first (as Autofill did earlier), then the ATS one replaces it
  await p.evaluate(() => {
    const f = new File(["x"], "base.pdf", { type: "application/pdf" }); const dt = new DataTransfer(); dt.items.add(f);
    const i = document.getElementById("r"); i.files = dt.files; i.dataset.riseplyAttached = "1";
  });
  await q("#riseply-attach-btn").click();
  await p.waitForFunction(() => document.getElementById("r").files[0].name === "tailored.pdf");

  // a file the person chose themselves is never replaced
  await p.evaluate(() => {
    const f = new File(["x"], "mine.pdf", { type: "application/pdf" }); const dt = new DataTransfer(); dt.items.add(f);
    const i = document.getElementById("r"); i.files = dt.files; delete i.dataset.riseplyAttached;
  });
  await q("#riseply-attach-btn").click();
  await q("#riseply-attach-msg .hint").waitFor();
  assert.equal(await fileName(), "mine.pdf");

  // marking applied is the person's own click
  assert.equal(await p.evaluate(() => window.__calls.filter((c) => c.type === "MARK_APPLIED").length), 0);
  await q("#riseply-applied-btn").click();
  await q("#riseply-applied-slot .filled-list").waitFor();
  const mark = await p.evaluate(() => window.__calls.find((c) => c.type === "MARK_APPLIED"));
  assert.equal(mark.applicationId, 7);
  // Autofill capitalizes an all-caps name, and the page's own Submit is offered with a confirm.
  await q("#riseply-fill-btn").click();
  await q("#riseply-filled-slot .filled-list").waitFor();
  assert.equal(await p.$eval("#n", (e) => e.value), "Jane Doe");
  assert.match(await q("#riseply-next-btn").innerText(), /Submit application/);
  await q("#riseply-next-btn").click();
  assert.equal(await p.evaluate(() => window.__submitted || 0), 0, "nothing is submitted before the confirm");
  await q("#riseply-next-yes").click();
  assert.equal(await p.evaluate(() => window.__submitted), 1);
  console.log("ok: sidebar ATS resume and applied");
  await b.close();
})().catch((e) => { console.error("FAIL ats", e.message); process.exit(1); });

// ---- Workday-style form: custom dropdowns, checkboxes, typeahead, date (seventh suite) ----
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const p = await b.newPage();
  await p.goto("file://" + path.join(__dirname, "fixture_workday.html"));
  await p.addScriptTag({ path: path.join(__dirname, "..", "profilefill.js") });
  const profile = {
    work: [], education: [], skills: [],
    saved_answers: [{ question: "Do you hold an active professional license or certification relevant to this role?", answer: "Yes" }],
    contact: { address_line1: "23751 Tall Grass Dr", city: "Plainfield", state: "IL", postal_code: "60585", country: "United States", phone_type: "" },
    answers: { over_18: "yes", needs_sponsorship: "no", previously_employed: "no", has_employee_relationship: "no", restrictive_agreement: "no",
      government_official: "no", related_to_official: "no", salary_expectation: "$150,000", referral_source: "Indeed" },
    eeo: { gender: "Man", hispanic: "No", race: "Black or African American", veteran: "No", disability: "No" },
  };
  const first = await p.evaluate((pr) => window.RisePlyFill.run(pr), profile);
  const done = await p.evaluate(() => window.RisePlyFill.finishCustom());
  const txt = (id) => p.$eval("#" + id, (e) => e.textContent);
  const val = (id) => p.$eval("#" + id, (e) => e.value);

  assert.equal(await txt("qlic"), "Yes", "a saved answer picks the option in a custom dropdown");
  assert.equal(await val("a1"), "23751 Tall Grass Dr");
  assert.equal(await val("ct"), "Plainfield");
  assert.equal(await val("pc"), "60585");
  assert.equal(await val("sal"), "150000", "annual salary box gets digits only");
  assert.equal(await p.$eval('input[name=prev][value=n]', (e) => e.checked), true, "previously worked here: No");
  assert.equal(await p.$eval("#d2", (e) => e.checked), true, "disability checkbox: No");
  assert.equal(await p.$eval("#d1", (e) => e.checked), false);
  assert.equal(await p.$eval("#d3", (e) => e.checked), false);
  assert.equal(await txt("country"), "United States of America");
  assert.equal(await txt("state"), "Illinois", "IL picks Illinois");
  assert.equal(await txt("ptype"), "Mobile", "phone type defaults to Mobile");
  assert.equal(await txt("q18"), "Yes");
  assert.equal(await txt("qspon"), "No");
  for (const id of ["qemp", "qrel", "qagr", "qgov", "qrgov"]) assert.equal(await txt(id), "No", id);
  assert.equal(await txt("qlast"), "Select One", "a question the profile doesn't answer is left alone");
  assert.equal(await txt("gender"), "Male");
  assert.equal(await txt("hisp"), "No");
  assert.equal(await txt("race"), "Black or African American (United States of America)");
  assert.equal(await txt("vet"), "I AM NOT A PROTECTED VETERAN", "not the 'identify as a veteran' option");
  assert.equal(await p.$eval('#heard ~ [data-automation-id=selectedItem], [data-automation-id=multiSelectContainer]:has(#heard) [data-automation-id=selectedItem]', (e) => e.textContent), "Indeed.com");
  assert.equal(await p.$eval('[data-automation-id=multiSelectContainer]:has(#pcode) [data-automation-id=selectedItem]', (e) => e.textContent), "United States of America (+1)");
  const today = new Date();
  assert.deepEqual(await p.$$eval('input[data-automation-id*=dateSection]', (e) => e.map((x) => x.value)),
    [String(today.getMonth() + 1).padStart(2, "0"), String(today.getDate()).padStart(2, "0"), String(today.getFullYear())]);
  assert.deepEqual(await p.evaluate(() => window.RisePlyFill.leftForYou()), ["is there anything else we should know about your availability this fall?"]);
  assert.equal(await p.evaluate(() => window.RisePlyFill.findAdvance().kind), "submit");
  assert.ok(done.includes("country") && done.includes("how you heard about the job"), done.join(","));
  console.log("ok: workday-style form:", first.filled.concat(done).join(", "));
  await b.close();
})().catch((e) => { console.error("FAIL workday", e.message); process.exit(1); });

// ---- a form inside an iframe (iCIMS, embedded Greenhouse): fill, attach, Next (eighth suite) ----
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const p = await b.newPage();
  const pdf = (t) => Buffer.from("%PDF-1.4 " + t).toString("base64");
  // Stands in for background.js: runs a request from the top frame inside the sub-frame.
  await p.exposeFunction("__frameOp", async (m) => {
    const fr = p.frames().find((f) => f !== p.mainFrame());
    const result = await fr.evaluate((req) => window.__rfListener({ type: "RF_OP", op: req.op, args: req.args }), m);
    return { success: true, results: [{ frameId: 1, result }] };
  });
  await p.addInitScript((files) => {
    if (window !== window.top) {
      window.chrome = { runtime: { id: "x", lastError: null, onMessage: { addListener(fn) { window.__rfListener = (msg) => new Promise((res) => fn(msg, {}, res)); } }, sendMessage(m, cb) { cb && cb({ success: true }); } } };
      return;
    }
    window.chrome = { runtime: { id: "x", lastError: null, sendMessage(m, cb) {
      const ok = (o) => setTimeout(() => cb({ success: true, ...o }), 0);
      if (m.type === "FRAME_OP") { window.__frameOp(m).then(cb); return; }
      if (m.type === "GET_AUTH_STATE") return ok({ loggedIn: true, user: { email: "a@b.c" } });
      if (m.type === "JOB_STATUS") return ok({ in_list: false });
      if (m.type === "GET_CANDIDATE") return ok({ candidate: { full_name: "JANE DOE", email: "j@x.com" } });
      if (m.type === "GET_AUTOFILL_PROFILE") return ok({ profile: { work: [], education: [], answers: {}, eeo: {}, saved_answers: [] } });
      if (m.type === "GET_RESUME_FILE") return ok({ filename: "base.pdf", content_type: "application/pdf", data: files.b });
      return ok({});
    } } };
  }, { b: pdf("base") });
  await p.goto("file://" + path.join(__dirname, "fixture_frame_host.html"));
  await p.waitForLoadState("load");
  while (p.frames().length < 2) await p.waitForTimeout(50);
  await p.frames().find((f) => f !== p.mainFrame()).waitForLoadState("load");
  for (const fr of p.frames()) for (const f of ["jobdetect.js", "jobinfo.js", "profilefill.js", "content.js"]) await fr.addScriptTag({ path: path.join(__dirname, "..", f) });
  const q = (sel) => p.locator("#riseply-sidebar-host " + sel);
  const fr = () => p.frames().find((f) => f !== p.mainFrame());
  assert.equal(await fr().locator("#riseply-sidebar-host").count(), 0, "no second sidebar inside the iframe");

  await q("#riseply-fill-btn").waitFor();
  await q("#riseply-fill-btn").click();
  await fr().waitForFunction(() => document.getElementById("r").files.length === 1);
  assert.equal(await fr().$eval("#fn", (e) => e.value), "Jane");
  assert.equal(await fr().$eval("#ln", (e) => e.value), "Doe");
  assert.equal(await fr().$eval("#em", (e) => e.value), "j@x.com");
  assert.equal(await fr().$eval("#r", (e) => e.files[0].name), "base.pdf", "resume attached inside the iframe");

  // Next lives in the iframe too: found, confirmed, then clicked there
  await q("#riseply-next-btn").waitFor();
  await q("#riseply-next-btn").click();
  assert.equal(await fr().evaluate(() => window.__clicked || 0), 0, "nothing clicked before the confirm");
  await q("#riseply-next-yes").click();
  await fr().waitForFunction(() => window.__clicked === 1);
  console.log("ok: form inside an iframe");
  await b.close();
})().catch((e) => { console.error("FAIL iframe", e.message); process.exit(1); });

// ---- job-page detection: only job pages get the panel (ninth suite) ----
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const filler = "<p>" + "Soft, comfortable tee in twelve colors with a tailored fit. ".repeat(40) + "</p>";
  const pages = {
    "https://www.ssactivewear.com/p/next_level/6211": ["<h1>Long Sleeve Tee</h1><button>Apply</button><button>Add to Cart</button>" + filler, false, "shop with an Apply filter button"],
    "https://shop.example.com/careers/gear": ["<h1>Careers gear</h1><button>Add to Cart</button><p>Resume your order. Requirements: none. Qualifications: none.</p>", false, "shop under a careers URL"],
    "https://blog.example.com/careers/our-office": ["<h1>Our new office</h1><p>We moved. Come say hi.</p>", false, "careers URL with no job words"],
    "https://www.example.com/news/story": ["<a href='#'>Apply</a>" + filler, false, "long page with only an Apply link"],
    "https://boards.greenhouse.io/acme/jobs/1": ["<h1>Anything</h1>", true, "known application site"],
    "https://acme.example.com/careers/analyst": ["<h1>Analyst</h1><h2>Responsibilities</h2><p>Qualifications: 3+ years of experience. Upload your resume.</p>", true, "company careers page with a job description"],
    "https://acme.example.com/open-role": ["<script type='application/ld+json'>{\"@type\":\"JobPosting\",\"title\":\"Analyst\"}</script><h1>Analyst</h1>", true, "page with JobPosting data"],
    "https://acme.example.com/work-with-us": ["<a href='#'>Apply now</a><h2>Responsibilities</h2><p>Qualifications: 3+ years of experience. Equal opportunity employer.</p>" + "<p>" + "Audit the controls and report to the team. ".repeat(50) + "</p>", true, "Apply button on a page that reads like a job"],
  };
  for (const [url, [html, want, label]] of Object.entries(pages)) {
    const p = await b.newPage();
    await p.route("**/*", (r) => r.fulfill({ contentType: "text/html", body: "<!doctype html><html><head><title>t</title></head><body>" + html + "</body></html>" }));
    await p.goto(url);
    await p.addScriptTag({ path: path.join(__dirname, "..", "jobdetect.js") });
    const got = await p.evaluate(() => window.RisePlyDetect.inspect());
    assert.equal(got.job, want, label + ": " + got.why);
    await p.close();
  }
  console.log("ok: only job pages are detected");
  await b.close();
})().catch((e) => { console.error("FAIL detection", e.message); process.exit(1); });

// ---- saved answers also pick dropdown and radio options (tenth suite) ----
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const p = await b.newPage();
  await p.goto("file://" + path.join(__dirname, "fixture_saved_choices.html"));
  await p.addScriptTag({ path: path.join(__dirname, "..", "profilefill.js") });
  const saved = [
    { question: "Do you have a valid driver's license?", answer: "Yes" },
    { question: "Are you willing to undergo a background check?", answer: "Yes." },
    { question: "Which best describes your current employment status?", answer: "Student" },
    { question: "What is your preferred work arrangement?", answer: "Remote" },
    { question: "Have you ever held a security clearance?", answer: "Public Trust" },
  ];
  const res = await p.evaluate((s) => window.RisePlyFill.run({ saved_answers: s }), saved);
  const sel = (id) => p.$eval("#" + id, (e) => e.value);
  assert.equal(await sel("dl"), "y", "yes picks the Yes option");
  assert.equal(await p.$eval('input[name=bg][value=y]', (e) => e.checked), true, "radio gets Yes");
  assert.equal(await p.$eval('input[name=bg][value=n]', (e) => e.checked), false);
  assert.equal(await sel("es"), "st", "same text picks that option");
  assert.equal(await sel("wa"), "", "two options contain 'Remote': left for the person");
  assert.equal(await sel("cl"), "", "an answer that is not an option is not guessed");
  assert.equal(await sel("al"), "", "a question with no saved answer is left alone");
  assert.equal(res.filled.filter((x) => x === "saved answer").length, 3);
  console.log("ok: saved answers pick dropdown and radio options");
  await b.close();
})().catch((e) => { console.error("FAIL saved choices", e.message); process.exit(1); });
