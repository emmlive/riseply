"use client";

import { useEffect, useId, useState } from "react";

// A side-column card that folds open and closed. The person's choice is
// remembered on this device; until they choose, `defaultOpen` decides (and may
// change as the page changes, e.g. past sessions open when no session is).
export default function Fold({ id, title, defaultOpen = true, note, aside, children }: {
  id: string;
  title: string;
  defaultOpen?: boolean;
  note?: string;          // small text beside the title while folded, e.g. "4 picks"
  aside?: React.ReactNode; // always visible on the right of the header, e.g. "Saved"
  children: React.ReactNode;
}) {
  const key = `cc-fold-${id}`;
  const [choice, setChoice] = useState<boolean | null>(null);
  const bodyId = useId();

  useEffect(() => {
    try {
      const v = localStorage.getItem(key);
      if (v === "1") setChoice(true);
      else if (v === "0") setChoice(false);
    } catch { /* storage unavailable: use the default */ }
  }, [key]);

  const open = choice ?? defaultOpen;
  function toggle() {
    const next = !open;
    setChoice(next);
    try { localStorage.setItem(key, next ? "1" : "0"); } catch { /* ignore */ }
  }

  return (
    <div className={`card fold ${open ? "is-open" : ""}`}>
      <div className="fold-head">
        <button type="button" className="fold-toggle" aria-expanded={open} aria-controls={bodyId} onClick={toggle}>
          <span className="fold-chevron" aria-hidden />
          <span className="fold-title">{title}</span>
          {!open && note && <span className="fold-note">{note}</span>}
        </button>
        {aside}
      </div>
      <div id={bodyId} className="fold-body" hidden={!open}>{children}</div>
    </div>
  );
}
