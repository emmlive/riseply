"use client";

import { CueStyle } from "@/lib/cues";

// One memory cue: a coloured card with an object beside the line. Cards for
// Remember and Write this down can drop the line straight into the notepad.
export default function MemoryCue({
  style, text, saved, onSave,
}: {
  style: CueStyle;
  text: string;
  saved: boolean;
  onSave?: () => void;
}) {
  return (
    <span className={`mc mc-${style.kind}`} role="note" aria-label={`${style.label}: ${text}`}>
      <span className="mc-object" role="img" aria-label={style.objectName}>{style.object}</span>
      <span className="mc-body">
        <span className="mc-label">{style.label}</span>
        <span className="mc-text">{text}</span>
        {style.canSave && onSave && (
          <button type="button" className="mc-save" onClick={onSave} disabled={saved}>
            {saved ? "Saved to my notes" : "Save to my notes"}
          </button>
        )}
      </span>
    </span>
  );
}

// A small legend above the conversation for whichever objects have appeared.
export function CueKey({ used }: { used: CueStyle[] }) {
  if (used.length === 0) return null;
  return (
    <ul className="mc-key" aria-label="What the cue objects mean">
      {used.map((c) => (
        <li key={c.kind}>
          <span aria-hidden>{c.object}</span> <strong>{c.label}</strong> {c.meaning.toLowerCase()}
        </li>
      ))}
    </ul>
  );
}
