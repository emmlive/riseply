// Run: node frontend/tests/speech.test.js  (uses the TypeScript compiler already in node_modules)
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const ts = require(path.join(__dirname, "..", "node_modules", "typescript"));

function load(file, req) {
  const src = fs.readFileSync(path.join(__dirname, "..", "lib", file), "utf8");
  const out = ts.transpileModule(src, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const mod = { exports: {} };
  new Function("module", "exports", "require", out)(mod, mod.exports, req || require);
  return mod.exports;
}
const cues = load("cues.ts");
const sp = load("speech.ts", (id) => (id === "@/lib/cues" ? cues : require(id)));
const { planSpeech, splitForSpeech, cleanForSpeech, spokenWordList, PAUSE } = sp;

const reply = `That's the right question to be asking, and honestly it's the question that separates people who know security from people who think like architects.

Here's the fundamental shift in mindset:

A security analyst asks "what happened and how do we fix it?"

A security architect asks "how do we build this so the bad thing never happens in the first place?"

An analyst is a detective. An architect is a city planner. The analyst shows up after the crime.`;

const plan = planSpeech(cleanForSpeech(reply));
const texts = plan.map((p) => p.text);

// 1. The words the voice says are exactly the words it said before: the read-along highlight depends on it.
const oldWords = splitForSpeech(cleanForSpeech(reply)).join(" ").split(/\s+/).filter(Boolean);
assert.deepEqual(spokenWordList(reply), oldWords);
for (const sample of [
  "Plain text. Two sentences here.",
  'He said "stop right there" and left. Then "no" again.',
  "- one\n- two\n- three\n\nAnd then a paragraph.",
  "An unbalanced \"quote here and more words. Fine.",
  "x ".repeat(300),
]) {
  const a = planSpeech(cleanForSpeech(sample)).map((p) => p.text).join(" ").split(/\s+/).filter(Boolean);
  const b = splitForSpeech(cleanForSpeech(sample)).join(" ").split(/\s+/).filter(Boolean);
  assert.deepEqual(a, b, `same words for: ${sample.slice(0, 30)}`);
}

// 2. Quotations are their own pieces, with a beat before and after.
const q1 = plan.findIndex((p) => p.text === '"what happened and how do we fix it?"');
assert.ok(q1 > 0, "the quotation is its own piece");
assert.equal(plan[q1].quoted, true);
assert.equal(plan[q1 - 1].text, "A security analyst asks");
assert.equal(plan[q1].gapBefore, PAUSE.quoteIn);
const q2 = plan.findIndex((p) => p.text.startsWith('"how do we build this'));
assert.equal(plan[q2].quoted, true);
assert.equal(plan.filter((p) => p.quoted).length, 2);

// 3. Paragraph breaks pause longer than line breaks; the very first piece never waits.
assert.equal(plan[0].gapBefore, 0);
const hereIs = plan.find((p) => p.text.startsWith("Here's the fundamental"));
assert.equal(hereIs.gapBefore, PAUSE.paragraph);
const list = planSpeech("Steps:\n- first\n- second\n\nDone.");
assert.deepEqual(list.map((p) => p.gapBefore), [0, PAUSE.line, PAUSE.line, PAUSE.paragraph]);

// 4. Narration after a quotation gets a beat too.
const after = planSpeech('He said "stop right there" and then he left.');
assert.deepEqual(after.map((p) => [p.text, p.quoted, p.gapBefore]), [
  ["He said", false, 0], ['"stop right there"', true, PAUSE.quoteIn], ["and then he left.", false, PAUSE.quoteOut],
]);
// curly quotes work the same; a lone quote mark is just text
assert.equal(planSpeech("She asked “why now” quietly").filter((p) => p.quoted).length, 1);
assert.equal(planSpeech('A lone " mark in text.').some((p) => p.quoted), false);

// 5. Abbreviations are not sentence ends and read as words.
const abbr = cleanForSpeech("Use controls, e.g. MFA, i.e. a second factor, vs. none, etc. Done.");
assert.equal(abbr, "Use controls, for example MFA, that is a second factor, versus none, and so on. Done.");
assert.equal(planSpeech(abbr).length, 1);

console.log("ok: speech prosody tests passed");
