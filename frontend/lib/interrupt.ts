// Interrupting the coach by voice.
//
// While the coach reads aloud, the microphone can listen for a short spoken
// command at the START of what you say: "wait" / "hold on" / "stop" (you have
// a question), or "go back" / "say that again" / "repeat that" (hear the last
// sentence again). Everything runs on the device with the browser's speech
// recognition; nothing is uploaded.
//
// The hard part is that on speakers the microphone also hears the coach. So
// anything that matches the words the coach is saying right now is ignored.
// The on-screen Wait and Back buttons never depend on this and always work.

export type Interruption =
  | { kind: "none" }
  | { kind: "wait"; rest: string }      // stop; `rest` is the question so far (may be empty)
  | { kind: "back" };                   // replay the last sentence

const WORD = /[\p{L}\p{N}']+/gu;
const norm = (t: string) => (t.toLowerCase().match(WORD) ?? []);

const WAIT = /^(wait|hold on|hang on|hold up|stop|pause|one second|one sec|just a sec(ond)?|excuse me|sorry|actually|i have a question|question)\b[\s,.!?-]*/i;
const BACK = /^(go back|back up|say that again|say it again|repeat that|repeat it|can you repeat( that)?|come again|what was that|what did you say|one more time)\b/i;

/** True when what the microphone heard is just the coach's own voice. */
export function isEcho(heard: string[], spoken: string[], at: number): boolean {
  if (!heard.length || !spoken.length) return false;
  const lo = Math.max(0, at - 30), hi = Math.min(spoken.length, at + 12);
  const near = new Set(spoken.slice(lo, hi).map((w) => norm(w).join("")).filter(Boolean));
  const hits = heard.filter((w) => near.has(w)).length;
  return heard.length <= 2 ? hits === heard.length : hits / heard.length >= 0.6;
}

// A command in the middle of a transcript has to be unmistakable: the words
// that are also ordinary speech ("actually", "sorry", "question") only count
// when they are the very first thing heard.
const WAIT_ANYWHERE = /^(wait|hold on|hang on|hold up|stop|pause|one second|one sec|just a sec(ond)?|excuse me|i have a question)\b[\s,.!?-]*/i;
const LOOK_BACK_WORDS = 14;

function nearSpoken(spoken: string[], at: number): Set<string> {
  const lo = Math.max(0, at - 30), hi = Math.min(spoken.length, at + 12);
  return new Set(spoken.slice(lo, hi).flatMap((w) => norm(w)));
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
  const near = nearSpoken(spoken, at);
  const first = Math.max(0, words.length - LOOK_BACK_WORDS);
  for (let i = first === 0 ? 0 : first; i < words.length; i++) {
    const phrase = words.slice(i).join(" ");
    const atStart = i === 0;
    const heardCommand = (m: RegExpMatchArray) => norm(m[0]).some((w) => near.has(w));
    const back = phrase.match(BACK);
    if (back && !heardCommand(back)) return { kind: "back" };
    const wait = phrase.match(atStart ? WAIT : WAIT_ANYWHERE);
    if (wait && !heardCommand(wait)) return { kind: "wait", rest: phrase.slice(wait[0].length).trim() };
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
  return transcript.trim().replace(WAIT, "").trim();
}
