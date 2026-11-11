// Run: node extension/tests/setvalue.test.js
const path = require("path");
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");
const assert = require("assert");
(async () => {
  const b = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const p = await b.newPage();
  await p.goto("file://" + path.join(__dirname, "fixture_strict_form.html"));
  await p.addScriptTag({ path: path.join(__dirname, "..", "profilefill.js") });
  await p.evaluate(() => window.RisePlyFill.setText(document.getElementById("fn"), "Emmanuel"));
  assert.equal(await p.evaluate(() => window.state.fn), "Emmanuel", "a typing-only component must see the value");
  assert.equal(await p.evaluate(() => window.touched.fn), true, "field must be marked visited");
  assert.equal(await p.$eval("#fn-err", (e) => e.textContent), "", "required message must clear");
  await b.close();
  console.log("ok");
})();
