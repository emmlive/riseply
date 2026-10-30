// Run: node frontend/tests/interrupt.test.js  (uses the TypeScript compiler already in node_modules)
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const ts = require(path.join(__dirname, "..", "node_modules", "typescript"));

const src = fs.readFileSync(path.join(__dirname, "..", "lib", "interrupt.ts"), "utf8");
const out = ts.transpileModule(src, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
const mod = { exports: {} };
new Function("module", "exports", out)(mod, mod.exports);
const { parseInterruption, isEcho } = mod.exports;

const coach = "After you put your controls in place some risk always remains. You can never reduce risk to zero. The risk that's left over after your controls are applied is called residual risk".split(" ");
const at = 14;   // the coach is around "the risk that's left over"

// headphones: the person's voice only
assert.deepEqual(parseInterruption("wait", coach, at), { kind: "wait", rest: "" });
assert.deepEqual(parseInterruption("hold on what does residual mean", coach, at), { kind: "wait", rest: "what does residual mean" });
assert.deepEqual(parseInterruption("go back", coach, at), { kind: "back" });
assert.deepEqual(parseInterruption("sorry can I ask something", coach, at), { kind: "wait", rest: "can I ask something" }, "weak openers still work at the start");

// speakers: the transcript begins with the coach's own voice, then the person speaks
const echo = "you can never reduce risk to zero the risk that's left over";
assert.deepEqual(parseInterruption(echo + " wait", coach, at), { kind: "wait", rest: "" }, "wait after the coach's voice");
assert.deepEqual(parseInterruption(echo + " wait what is residual risk", coach, at), { kind: "wait", rest: "what is residual risk" });
assert.deepEqual(parseInterruption(echo + " go back", coach, at), { kind: "back" });
assert.deepEqual(parseInterruption(echo + " say that again", coach, at), { kind: "back" });

// the coach's own voice alone is never a command
assert.deepEqual(parseInterruption(echo, coach, at), { kind: "none" });
// ordinary words in the middle are not commands
assert.deepEqual(parseInterruption(echo + " actually", coach, at), { kind: "none" }, "weak words only count at the start");
assert.deepEqual(parseInterruption(echo + " sorry", coach, at), { kind: "none" });
// a command word the coach is saying right now is not the person
const coach2 = "so wait for the approval before you ship it".split(" ");
assert.deepEqual(parseInterruption("so wait for the approval", coach2, 3), { kind: "none" }, "coach says wait");
assert.deepEqual(parseInterruption("", coach, at), { kind: "none" });
assert.ok(isEcho(["the", "risk"], coach, at));
console.log("ok: voice interrupt hears wait and go back, on headphones and on speakers");
