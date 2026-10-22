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
