"use client";

import "./SessionFlags.css";

export type SessionFlag = "" | "continue" | "keep" | "discard";

export const FLAGS: { value: Exclude<SessionFlag, "">; label: string; hint: string }[] = [
  { value: "continue", label: "Continue", hint: "I want to pick this up again" },
  { value: "keep", label: "Keep", hint: "Done, but worth keeping" },
  { value: "discard", label: "Not keeping", hint: "I don't need this one" },
];

// The three color chips under a past session. Press the one that is on to clear it.
export function FlagChips({ flag, onFlag, onDelete }: {
  flag: SessionFlag; onFlag: (f: SessionFlag) => void; onDelete: () => void;
}) {
  return (
    <div className="sf-chips" role="group" aria-label="Mark this session">
      {FLAGS.map((f) => (
        <button
          key={f.value} type="button" title={f.hint}
          className={`sf-chip sf-${f.value} ${flag === f.value ? "is-on" : ""}`}
          aria-pressed={flag === f.value}
          onClick={() => onFlag(flag === f.value ? "" : f.value)}
        >
          {f.label}
        </button>
      ))}
      <button type="button" className="sf-delete" onClick={onDelete}>Delete</button>
    </div>
  );
}

// Filter the list by mark, and delete everything marked "Not keeping" at once.
export function FlagFilter({ counts, value, onChange, onDeleteDiscarded, busy }: {
  counts: Record<SessionFlag | "all", number>; value: SessionFlag | "all";
  onChange: (v: SessionFlag | "all") => void; onDeleteDiscarded: () => void; busy: boolean;
}) {
  const marked = counts.continue + counts.keep + counts.discard;
  if (!marked) {
    return <p className="hint sf-intro">Mark sessions as Continue, Keep or Not keeping to sort them out. Marks are only for you.</p>;
  }
  return (
    <div className="sf-filter">
      <div className="sf-filter-row" role="group" aria-label="Show sessions">
        <button type="button" className={`sf-fchip ${value === "all" ? "is-on" : ""}`} onClick={() => onChange("all")}>All {counts.all}</button>
        {FLAGS.map((f) => (
          <button key={f.value} type="button" className={`sf-fchip sf-${f.value} ${value === f.value ? "is-on" : ""}`} onClick={() => onChange(f.value)}>
            {f.label} {counts[f.value]}
          </button>
        ))}
      </div>
      {counts.discard > 0 && (
        <button type="button" className="sf-bulk" disabled={busy} onClick={onDeleteDiscarded}>
          {busy ? "Deleting…" : `Delete the ${counts.discard} marked Not keeping`}
        </button>
      )}
    </div>
  );
}
