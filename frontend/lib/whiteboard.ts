import type { CareerCoachVisual } from "@/lib/api";

// Which part of the drawing the coach is talking about right now.
//
// The board is read as a list of parts (steps, rows, branches, bars, quadrants).
// Each part is matched to the first moment the spoken words mention it, using
// the longest word of its label (4+ letters). As the voice moves on, the board
// points at the last part that has been mentioned. If the coach never names any
// part, the pointer simply follows progress through the words.

function parts(v: CareerCoachVisual): string[] {
  switch (v.kind) {
    case "flow": case "cycle": case "layers": return v.steps.map((s) => s.label);
    case "compare": return v.rows.map((r) => r.label);
    case "map": return [v.center, ...v.branches.map((b) => b.label)];
    case "matrix": return (v.quadrants ?? []).map((q) => q.label);
    case "chart": return (v.bars ?? []).map((b) => b.label);
  }
  return [];
}

const norm = (w: string) => w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");

function keyWord(label: string): string {
  const words = label.split(/\s+/).map(norm).filter((w) => w.length >= 4);
  return words.sort((a, b) => b.length - a.length)[0] ?? "";
}

/** Index of the part to point at, or -1 for none yet. `spoken` = words as read aloud, `at` = word number reached. */
export function focusIndex(v: CareerCoachVisual, spoken: string[], at: number): number {
  const labels = parts(v);
  if (!labels.length || at < 0 || !spoken.length) return -1;
  const words = spoken.map(norm);
  const firsts = labels.map((l) => {
    const k = keyWord(l);
    if (!k) return -1;
    const stem = k.length > 5 ? k.slice(0, k.length - 1) : k;   // "loops" matches "loop"
    return words.findIndex((w) => w.startsWith(stem));
  });
  if (firsts.every((f) => f < 0)) {
    return Math.min(labels.length - 1, Math.floor((at / Math.max(1, spoken.length)) * labels.length));
  }
  let best = -1;
  firsts.forEach((f, i) => { if (f >= 0 && f <= at && (best < 0 || f >= firsts[best])) best = i; });
  return best;
}
