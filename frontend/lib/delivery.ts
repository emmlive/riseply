// How a spoken answer was delivered, worked out in the browser from the
// dictated text and the time taken. Numbers only: no audio leaves the device.

export interface Delivery {
  seconds: number;
  words: number;
  wpm: number;
  fillers: Record<string, number>;
}

// Phrases that pad an answer. Speech-to-text often drops "um" and "uh", so
// this undercounts: the coach is told it is a floor, not a full count.
const FILLERS = ["you know", "i mean", "basically", "actually", "literally", "sort of", "kind of", "um", "uh", "er"];

export function countWords(text: string): number {
  const m = text.trim().match(/\S+/g);
  return m ? m.length : 0;
}

export function analyzeDelivery(text: string, seconds: number): Delivery {
  const words = countWords(text);
  const secs = Math.max(0, Math.round(seconds));
  const fillers: Record<string, number> = {};
  const lower = ` ${text.toLowerCase().replace(/[^a-z' ]+/g, " ")} `;
  for (const f of FILLERS) {
    const re = new RegExp(`\\s${f}\\s`, "g");
    const n = (lower.match(re) || []).length;
    if (n > 0) fillers[f] = n;
  }
  // Pace is meaningless over a few seconds.
  const wpm = secs >= 5 ? Math.round(words / (secs / 60)) : 0;
  return { seconds: Math.min(secs, 900), words: Math.min(words, 5000), wpm: Math.min(wpm, 500), fillers };
}

export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// One short line for a message: "1:14 · 146 wpm · 4 filler words".
export function deliveryLabel(d: Delivery): string {
  const fillerTotal = Object.values(d.fillers).reduce((a, b) => a + b, 0);
  const parts = [clock(d.seconds)];
  if (d.wpm > 0) parts.push(`${d.wpm} wpm`);
  if (fillerTotal > 0) parts.push(`${fillerTotal} filler ${fillerTotal === 1 ? "word" : "words"}`);
  return parts.join(" · ");
}

// A plain-English read of the pace, for the little chip under an answer.
export function paceNote(d: Delivery): string {
  if (d.wpm === 0) return "";
  if (d.wpm < 100) return "on the slow side";
  if (d.wpm > 180) return "on the fast side";
  return "a natural pace";
}
