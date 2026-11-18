// Run: node extension/tests/hostcompany.test.js
const fs = require("fs"), path = require("path"), assert = require("assert");
global.window = {}; global.document = { querySelectorAll: () => [], querySelector: () => null }; global.location = { hostname: "x.com" };
eval(fs.readFileSync(path.join(__dirname, "..", "jobinfo.js"), "utf8"));
const h = window.RisePlyJob.hostCompany;
assert.equal(h("apply.constellationbrands.com"), "constellationbrands");
assert.equal(h("careers.acme.com"), "acme");
assert.equal(h("www.acme.com"), "acme");
assert.equal(h("constellation.wd5.myworkdayjobs.com"), "constellation");
assert.equal(h("jobs.lever.co"), "lever");
assert.equal(h("job-boards.greenhouse.io","/kairospower/jobs/6102019004"),"kairospower");
assert.equal(h("jobs.lever.co","/acme/abc"),"acme");
assert.equal(h("boards.greenhouse.io","/embed/job_app"),"greenhouse");
console.log("ok");
