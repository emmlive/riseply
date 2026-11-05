// Interrupting the coach by voice.
//
// While the coach reads aloud, the microphone can listen for a short spoken
// command: "wait" / "hold on" / "stop" (you have a question), or "go back" /
// "say that again" / "repeat that" (hear the last sentence again). Everything
// runs on the device with the browser's speech recognition; nothing is uploaded.
//
// The hard part is that on speakers the microphone also hears the coach. So a
// command is ignored if the coach's reply contains those same words anywhere.
// The on-screen Wait and Back buttons never depend on this and always work.

export type Interruption =
  | { kind: "none" }
  | { kind: "wait"; rest: string }      // stop; `rest` is the question so far (may be empty)
  | { kind: "back" };                   // replay the last sentence

const WORD = /[\p{L}\p{N}']+/gu;
const norm = (t: string) => (t.toLowerCase().match(WORD) ?? []);

// What counts as a command. Ordinary words that people (and the coach) say all
// the time ("actually", "sorry", "question", "back up", "one more time") are NOT
// commands: on speakers the microphone hears the coach, and those words cut the
// coach off for no reason.
const WAIT = /^(wait|hold on|hang on|hold up|stop|pause|one second|one sec|just a sec(ond)?|i have a question)\b[\s,.!?-]*/i;
const BACK = /^(go back|say that again|say it again|repeat that|repeat it|can you repeat( that)?|what did you say)\b/i;
// Used only to strip a lead-in from what the person said after they cut in.
const LEAD_IN = /^(wait|hold on|hang on|hold up|stop|pause|one second|one sec|just a sec(ond)?|excuse me|sorry|actually|i have a question|question)\b[\s,.!?-]*/i;

/** True when what the microphone heard is just the coach's own voice. */
export function isEcho(heard: string[], spoken: string[], at: number): boolean {
  if (!heard.length || !spoken.length) return false;
  const lo = Math.max(0, at - 30), hi = Math.min(spoken.length, at + 12);
  const near = new Set(spoken.slice(lo, hi).map((w) => norm(w).join("")).filter(Boolean));
  const hits = heard.filter((w) => near.has(w)).length;
  return heard.length <= 2 ? hits === heard.length : hits / heard.length >= 0.6;
}

const LOOK_BACK_WORDS = 14;

// True when the coach's reply (the WHOLE reply, not just the stretch being read
// now: the voice position is only an estimate and the microphone lags behind
// it) contains these words in a row. Then it is most likely the coach, not you.
function inReply(spoken: string[], phrase: string[]): boolean {
  if (!phrase.length) return false;
  const all = spoken.flatMap((w) => norm(w));
  for (let i = 0; i + phrase.length <= all.length; i++) {
    if (phrase.every((w, j) => all[i + j] === w)) return true;
  }
  return false;
}

// What follows a command is the person's own question, so it should NOT be the
// coach's words. A recognizer often mishears the coach ("what happens when" ->
// "wait happens when"); when the words after the "command" are a run of the
// reply, it was the coach.
function echoesReply(words: string[], spoken: string[]): boolean {
  if (words.length < 3) return false;
  for (let i = 0; i + 3 <= words.length; i++) {
    if (inReply(spoken, words.slice(i, i + 3))) return true;
  }
  return false;
}

/** How long a bare or short command must stay the latest thing heard before it counts. */
export const CONFIRM_MS = 700;

/**
 * A command that is just "wait" (or has under three words after it), or any
 * "go back", could still be a mishearing of the coach, so it is only acted on
 * once nothing more has been heard for CONFIRM_MS. A longer question goes
 * straight through.
 */
export function needsConfirm(r: Interruption): boolean {
  if (r.kind === "back") return true;
  return r.kind === "wait" && r.rest.split(/\s+/).filter(Boolean).length < 3;
}

/**
 * What the person said (`transcript` = everything heard since listening
 * started), judged against the words being read aloud.
 *
 * The transcript is cumulative. On speakers it starts with the coach's own
 * voice, so a command is looked for among the latest words, not only at the
 * start. A command word the coach is saying right now is not a command.
 */
export function parseInterruption(transcript: string, spoken: string[], at: number): Interruption {
  const text = transcript.trim();
  if (!text) return { kind: "none" };
  const words = text.split(/\s+/);
  const first = Math.max(0, words.length - LOOK_BACK_WORDS);
  for (let i = first === 0 ? 0 : first; i < words.length; i++) {
    const phrase = words.slice(i).join(" ");
    const heardCommand = (m: RegExpMatchArray) => inReply(spoken, norm(m[0]));
    const back = phrase.match(BACK);
    if (back && !heardCommand(back) && !echoesReply(norm(phrase.slice(back[0].length)), spoken)) return { kind: "back" };
    const wait = phrase.match(WAIT);
    if (wait && !heardCommand(wait)) {
      const rest = phrase.slice(wait[0].length).trim();
      if (!echoesReply(norm(rest), spoken)) return { kind: "wait", rest };
    }
  }
  // Only the person's own voice (headphones), no command: nothing to do.
  return { kind: "none" };
}

/**
 * Index of the first word of the sentence to replay. `at` is the word being
 * spoken. When the voice has only just started a sentence, going back means the
 * one before it.
 */
export function sentenceStart(words: string[], at: number): number {
  if (!words.length) return 0;
  const i = Math.max(0, Math.min(at, words.length - 1));
  const ends = (w: string) => /[.!?]["')\]]*$/.test(w);
  let start = i;
  while (start > 0 && !ends(words[start - 1])) start--;
  if (i - start < 3 && start > 0) {   // barely into this sentence: go to the previous one
    start--;
    while (start > 0 && !ends(words[start - 1])) start--;
  }
  return start;
}

/** The last stretch of what the person heard, to tell the coach where they cut in. */
export function heardTail(words: string[], at: number, max = 40): string {
  if (at < 0) return "";
  return words.slice(Math.max(0, at - max + 1), at + 1).join(" ");
}

/** What is left of a spoken utterance after its leading "wait" (the question itself). */
export function restAfterWait(transcript: string): string {
  return transcript.trim().replace(LEAD_IN, "").trim();
}
