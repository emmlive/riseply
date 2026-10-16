import { CueStyle, parseCueLine } from "@/lib/cues";

// Read-along: lines up the words the voice is saying with the words on the
// screen, so the one being spoken can be highlighted. The voice reads a
// cleaned-up copy of the reply (no asterisks, links shortened, cue labels
// added), so the two word lists differ a little; alignSpoken() pairs them up
// and simply skips the words that exist on only one side.

export function norm(word: string): string {
  return (word || "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
}

export interface Tok { s: string; w: number; p: number } // a chunk of text; w = word number (-1 for spaces / symbols); p = the word just before
export interface TextPart { bold: boolean; toks: Tok[] }
export type Line =
  | { kind: "rule" }
  | { kind: "cue"; style: CueStyle; text: string; start: number; end: number }
  | { kind: "text"; parts: TextPart[]; last: boolean };

export interface Layout {
  lines: Line[];
  words: string[];        // normalised on-screen words, in order
  sentence: number[];     // sentence number of each word
}

const RULE = /^\s*(-{3,}|\*{3,}|_{3,})\s*$/;
const SENTENCE_END = /[.!?]["')\]]*$/;

// Splits the coach's reply the same way it is drawn: rules, memory cues, and
// text with **bold** parts, numbering each word as it goes.
export function layoutCoachText(text: string): Layout {
  const lines: Line[] = [];
  const words: string[] = [];
  const sentence: number[] = [];
  let sent = 0;
  const lineList = (text || "").split("\n");
  lineList.forEach((line, i) => {
    if (RULE.test(line)) { lines.push({ kind: "rule" }); return; }
    const cue = parseCueLine(line);
    if (cue) {
      const start = words.length;
      for (const raw of cue.text.split(/\s+/)) {
        const n = norm(raw);
        if (!n) continue;
        words.push(n); sentence.push(sent);
      }
      sent++;
      lines.push({ kind: "cue", style: cue.style, text: cue.text, start, end: words.length });
      return;
    }
    const parts: TextPart[] = line.split(/\*\*(.+?)\*\*/g).map((part, j) => {
      let prev = words.length - 1;
      const toks: Tok[] = part.split(/(\s+)/).filter((s) => s !== "").map((s) => {
        const n = /\s/.test(s[0]) ? "" : norm(s);
        if (!n) return { s, w: -1, p: prev };
        const w = words.length;
        words.push(n); sentence.push(sent);
        if (SENTENCE_END.test(s)) sent++;
        prev = w;
        return { s, w, p: prev };
      });
      return { bold: j % 2 === 1, toks };
    });
    sent++;   // a new line starts a new sentence
    lines.push({ kind: "text", parts, last: i === lineList.length - 1 });
  });
  return { lines, words, sentence };
}

// For every spoken word, the on-screen word it matches (or -1).
export function alignSpoken(display: string[], spoken: string[]): number[] {
  const LOOK = 12;
  const out: number[] = [];
  let cursor = 0;
  let misses = 0;
  const sn = spoken.map(norm);
  for (let k = 0; k < sn.length; k++) {
    const s = sn[k];
    if (!s) { out.push(-1); continue; }
    let found = -1;
    const end = Math.min(display.length, cursor + LOOK);
    for (let j = cursor; j < end; j++) if (display[j] === s) { found = j; break; }
    // Lost the place (a long stretch the voice skipped, such as a code block):
    // jump ahead to the next spot where two words in a row agree.
    if (found < 0 && misses >= 3) {
      for (let j = cursor; j < display.length; j++) {
        if (display[j] === s && (k + 1 >= sn.length || !sn[k + 1] || display[j + 1] === sn[k + 1])) { found = j; break; }
      }
    }
    if (found >= 0) { out.push(found); cursor = found + 1; misses = 0; }
    else { out.push(-1); misses++; }
  }
  return out;
}

// cur[k] = the on-screen word to highlight when spoken word k is being said.
export function currentWordTable(map: number[]): number[] {
  const cur: number[] = [];
  let last = -1;
  for (const j of map) { if (j > last) last = j; cur.push(last); }
  return cur;
}
