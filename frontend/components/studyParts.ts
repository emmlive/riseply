// Splits a coach reply into pieces the person can tick: each paragraph, and
// each bullet or numbered line of a list. Joins the ticked pieces back
// together, keeping list lines on their own lines.

export interface StudyPart { id: number; text: string; para: number }

const BULLET = /^\s*(?:[-*•▪◦]|\d{1,2}[.)])\s+/;

export function splitParts(content: string): StudyPart[] {
  const parts: StudyPart[] = [];
  const paras = content.split(/\n{2,}/).map((p) => p.trim()).filter((p) => p && !/^[-*_]{3,}$/.test(p));
  paras.forEach((p, para) => {
    const lines = p.split("\n").map((l) => l.trim()).filter(Boolean);
    if (lines.filter((l) => BULLET.test(l)).length >= 2) {
      let cur = "";
      const flush = () => { if (cur) parts.push({ id: parts.length, text: cur, para }); cur = ""; };
      for (const l of lines) {
        if (BULLET.test(l) || !cur) { flush(); cur = l; } else cur += " " + l;
      }
      flush();
    } else {
      parts.push({ id: parts.length, text: lines.join("\n"), para });
    }
  });
  return parts;
}

export function joinParts(parts: StudyPart[], picked: Set<number>): string {
  let out = "";
  let prev: StudyPart | null = null;
  for (const p of parts) {
    if (!picked.has(p.id)) continue;
    out += prev ? (prev.para === p.para ? "\n" : "\n\n") : "";
    out += p.text;
    prev = p;
  }
  return out;
}
