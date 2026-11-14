// Run: node extension/tests/description.test.js
// The text sent for tailoring and scoring must be the posting, not the whole page.
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");
const assert = require("assert");
const path = require("path");

const JD = `<h2>About the role</h2><p>You will lead third-party security due diligence for private equity clients.</p>
<h3>Responsibilities</h3><ul><li>Assess vendor controls against NIST CSF and SOC 2</li><li>Write board-ready findings</li></ul>
<h3>Requirements</h3><ul><li>7+ years of IT audit or security consulting experience</li><li>CISA or CISSP preferred</li><li>Experience with M&A transaction diligence</li></ul>
<h3>Benefits</h3><p>Health, 401k, equity, flexible schedule. We are an equal opportunity employer.</p>`;
const FILLER = (n) => Array.from({ length: n }, (_, i) => `<li><a href="/job/${i}">Other Job ${i} Engineer, Acme ${i}, Remote</a></li>`).join("");
const LONG_INTRO = "<p>" + "We are a global company with a long history of excellence and a culture you will love. ".repeat(90) + "</p>";

const pages = {
  // the site's own description box, buried under 100 other jobs in a side list
  linkedinLike: `<body><nav><a href="/">Home</a><a href="/jobs">Jobs</a></nav><ul>${FILLER(120)}</ul>
    <div class="jobs-description__content">${JD}</div><footer>Privacy Policy User Agreement</footer></body>`,
  // structured data wins, whatever the markup looks like
  jsonLd: `<head><script type="application/ld+json">${JSON.stringify({ "@type": "JobPosting", title: "Associate Partner",
    description: JD })}</script></head><body><nav>${FILLER(80)}</nav><main><p>Loading...</p></main></body>`,
  // no known box, no structured data: the densest posting-like block, not the menus
  unknownSite: `<body><header><nav>${FILLER(100)}</nav></header><main><div class="wrap"><div class="x1">${LONG_INTRO}</div>
    <div class="x2">${JD}</div></div></main><footer><a href="/p">Privacy</a><a href="/t">Terms</a></footer></body>`,
  // the posting is more than 6,000 characters down the page: the old whole-page text lost it
  buriedPosting: `<body><div id="menus">${FILLER(300)}</div><div class="job-description">${JD}</div></body>`,
};

(async () => {
  const b = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const p = await b.newPage();
  for (const [name, html] of Object.entries(pages)) {
    await p.goto("data:text/html;charset=utf-8," + encodeURIComponent(html.startsWith("<head") ? `<!doctype html><html>${html}</html>` : `<!doctype html><html>${html}</html>`));
    await p.addScriptTag({ path: path.join(__dirname, "..", "jobinfo.js") });
    const d = await p.evaluate(() => window.RisePlyJob.description());
    assert.match(d, /Assess vendor controls against NIST CSF/, name + ": has the responsibilities");
    assert.match(d, /CISA or CISSP preferred/, name + ": has the requirements");
    assert.doesNotMatch(d, /Other Job \d+ Engineer/, name + ": no other jobs from the side list");
    assert.doesNotMatch(d, /Privacy Policy|User Agreement|Loading\.\.\./, name + ": no page chrome");
    assert.ok(d.length < (name === "unknownSite" ? 12000 : 4000), name + ": just the posting, " + d.length + " chars");
    console.log("ok:", name);
  }
  // a page with nothing posting-like still returns its text rather than nothing
  await p.goto("data:text/html," + encodeURIComponent("<!doctype html><body><p>" + "Plain page text. ".repeat(40) + "</p></body>"));
  await p.addScriptTag({ path: path.join(__dirname, "..", "jobinfo.js") });
  assert.match(await p.evaluate(() => window.RisePlyJob.description()), /Plain page text/);
  await b.close();
  console.log("ok");
})().catch((e) => { console.error(e); process.exit(1); });
