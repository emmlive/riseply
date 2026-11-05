// Run: node frontend/tests/interrupt.test.js  (uses the TypeScript compiler already in node_modules)
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const ts = require(path.join(__dirname, "..", "node_modules", "typescript"));

const src = fs.readFileSync(path.join(__dirname, "..", "lib", "interrupt.ts"), "utf8");
const out = ts.transpileModule(src, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
const mod = { exports: {} };
new Function("module", "exports", out)(mod, mod.exports);
const { parseInterruption, isEcho, needsConfirm } = mod.exports;

const coach = "After you put your controls in place some risk always remains. You can never reduce risk to zero. The risk that's left over after your controls are applied is called residual risk".split(" ");
const at = 14;   // the coach is around "the risk that's left over"

// headphones: the person's voice only
assert.deepEqual(parseInterruption("wait", coach, at), { kind: "wait", rest: "" });
assert.deepEqual(parseInterruption("hold on what does residual mean", coach, at), { kind: "wait", rest: "what does residual mean" });
assert.deepEqual(parseInterruption("go back", coach, at), { kind: "back" });
assert.deepEqual(parseInterruption("i have a question what is residual risk", coach, at), { kind: "wait", rest: "what is residual risk" });
assert.deepEqual(parseInterruption("sorry can I ask something", coach, at), { kind: "none" }, "everyday words are not commands");

// speakers: the transcript begins with the coach's own voice, then the person speaks
const echo = "you can never reduce risk to zero the risk that's left over";
assert.deepEqual(parseInterruption(echo + " wait", coach, at), { kind: "wait", rest: "" }, "wait after the coach's voice");
assert.deepEqual(parseInterruption(echo + " wait what is residual risk", coach, at), { kind: "wait", rest: "what is residual risk" });
assert.deepEqual(parseInterruption(echo + " go back", coach, at), { kind: "back" });
assert.deepEqual(parseInterruption(echo + " say that again", coach, at), { kind: "back" });

// the coach's own voice alone is never a command
assert.deepEqual(parseInterruption(echo, coach, at), { kind: "none" });
// ordinary words in the middle are not commands
assert.deepEqual(parseInterruption(echo + " actually", coach, at), { kind: "none" }, "everyday words are never commands");
assert.deepEqual(parseInterruption(echo + " sorry", coach, at), { kind: "none" });
// a command word the coach is saying right now is not the person
const coach2 = "so wait for the approval before you ship it".split(" ");
assert.deepEqual(parseInterruption("so wait for the approval", coach2, 3), { kind: "none" }, "coach says wait");
assert.deepEqual(parseInterruption("", coach, at), { kind: "none" });
assert.ok(isEcho(["the", "risk"], coach, at));

// Regression: the coach was cut off mid-explanation with nobody speaking. The
// microphone heard the coach's own everyday words, and the voice position is
// only an estimate, so a command word far from it still fired.
const reply = ("That's the right question to be asking. Actually it separates people who know security from people who think like architects. " +
  "You should back up your keys and stop trusting defaults. Let's walk through it one more time. Sorry, what was that control called? " +
  "Hold on to the idea that an architect designs the city. Come again to the part about scope later.").split(" ");
for (const at2 of [-1, 0, 3, 12, 30, 60]) {
  for (const heard of [
    "question to be asking actually it separates",
    "back up your keys and stop trusting defaults",
    "walk through it one more time sorry what was that control",
    "hold on to the idea that an architect designs the city",
    "come again to the part about scope",
    "actually", "sorry", "question", "back up", "one more time", "what was that", "come again",
  ]) {
    assert.deepEqual(parseInterruption(heard, reply, at2), { kind: "none" }, `echo "${heard}" at ${at2} must not interrupt`);
  }
}
// ...and a real interruption still works when the coach never says those words
const plain = "Here is the fundamental shift in mindset an analyst fixes problems and an architect prevents them".split(" ");
assert.deepEqual(parseInterruption("here is the fundamental shift wait", plain, -1), { kind: "wait", rest: "" });
assert.deepEqual(parseInterruption("hold on what does fundamental mean", plain, -1), { kind: "wait", rest: "what does fundamental mean" });
assert.deepEqual(parseInterruption("here is the shift go back", plain, 4), { kind: "back" });
assert.equal(mod.exports.restAfterWait("sorry what does that mean"), "what does that mean");

// Mishearing: the recognizer turns the coach's "what happens when an attacker
// gets in" into "wait happens when an attacker gets in". The words after the
// "command" are the coach's, so it is not a command.
const reply2 = 'Instead of thinking "how do I keep attackers out?" you think "what happens when an attacker gets in?" Because they will eventually.'.split(" ");
assert.deepEqual(parseInterruption("wait happens when an attacker gets in", reply2, 5), { kind: "none" });
assert.deepEqual(parseInterruption("you think wait happens when an attacker", reply2, 5), { kind: "none" });
assert.deepEqual(parseInterruption("stop what happens when", reply2, -1), { kind: "none" });
// ...while a real question after "wait" still goes through, even quoting a word of the reply
assert.deepEqual(parseInterruption("wait what does attacker mean here", reply2, 5), { kind: "wait", rest: "what does attacker mean here" });
// a bare command, or a short one, waits to be confirmed; a real question does not
assert.equal(needsConfirm({ kind: "wait", rest: "" }), true);
assert.equal(needsConfirm({ kind: "wait", rest: "what now" }), true);
assert.equal(needsConfirm({ kind: "back" }), true);
assert.equal(needsConfirm({ kind: "wait", rest: "what does residual risk mean" }), false);
assert.equal(needsConfirm({ kind: "none" }), false);
console.log("ok: voice interrupt hears wait and go back, on headphones and on speakers");
