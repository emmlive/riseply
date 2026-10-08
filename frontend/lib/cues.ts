// Memory cues: the coach can pin one line to a card with an object beside it.
// The coach writes the line as  [[cue:remember]] The line itself.
// This file is the one place the frontend knows the marker format.

export type CueKind = "remember" | "write" | "watch" | "try";

export interface CueStyle {
  kind: CueKind;
  object: string;      // the emoji shown beside the line
  objectName: string;  // for screen readers and the key
  label: string;       // spoken aloud and shown on the card
  meaning: string;     // one line in the key
  canSave: boolean;    // offers "Save to my notes"
}

export const CUES: CueStyle[] = [
  { kind: "remember", object: "\u{1F418}", objectName: "Elephant", label: "Remember", meaning: "Worth locking in", canSave: true },
  { kind: "write", object: "\u{1F4DD}", objectName: "Memo", label: "Write this down", meaning: "Put it in your notes", canSave: true },
  { kind: "watch", object: "\u{1F6A9}", objectName: "Flag", label: "Watch out", meaning: "A common trap", canSave: false },
  { kind: "try", object: "\u{1F4A1}", objectName: "Light bulb", label: "Try this", meaning: "Practice it next", canSave: false },
];

const BY_KIND = new Map(CUES.map((c) => [c.kind, c]));

// A cue is a whole line that starts with the marker.
const LINE = /^[ \t]*\[\[cue:([a-z]+)\]\][ \t]*(.*)$/i;

export function parseCueLine(line: string): { style: CueStyle; text: string } | null {
  const m = LINE.exec(line);
  if (!m) return null;
  const style = BY_KIND.get(m[1].toLowerCase() as CueKind);
  const text = m[2].trim();
  return style && text ? { style, text } : null;
}

// The line as it goes into the notepad: the object first, then the words.
export function cueNoteLine(style: CueStyle, text: string): string {
  return `${style.object} ${text}`;
}

// Which cue types appear in these replies, in key order, for the key.
export function cuesUsed(texts: string[]): CueStyle[] {
  const seen = new Set<CueKind>();
  for (const t of texts) {
    for (const line of t.split("\n")) {
      const c = parseCueLine(line);
      if (c) seen.add(c.style.kind);
    }
  }
  return CUES.filter((c) => seen.has(c.kind));
}

// Reply text with each cue written as "<object> line", for saving a whole
// reply to a study folder.
export function cuesToNoteText(text: string): string {
  return text
    .split("\n")
    .map((line) => {
      const c = parseCueLine(line);
      return c ? cueNoteLine(c.style, c.text) : line;
    })
    .join("\n");
}

// Read aloud: "Remember: line", never the emoji's name or the raw marker.
export function cuesToSpeech(text: string): string {
  return text
    .split("\n")
    .map((line) => {
      const c = parseCueLine(line);
      return c ? `${c.style.label}: ${c.text}` : line.replace(/\[\[\/?cue[^\]]*\]\]/gi, "");
    })
    .join("\n");
}
