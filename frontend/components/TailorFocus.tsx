"use client";

import { useState } from "react";
import "./TailorFocus.css";

// Tell Riseply how to point this resume ("Security Architect; keep every role
// on security, don't make me look like a developer") and rebuild it. The
// direction is saved with the job, so later re-tailors keep it. It only changes
// emphasis and wording: Riseply still never adds experience you don't have.
export const FOCUS_EXAMPLE = "Tailor this for a Security Architect role. Keep every role focused on security architecture and governance. Don't make me look like a developer.";

export default function TailorFocus({ saved, busy, onRetailor }: {
  saved: string; busy: boolean; onRetailor: (focus: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(saved);

  async function go() {
    await onRetailor(text.trim());
    setOpen(false);
  }

  if (!open) {
    return (
      <div className="tf">
        <button className="btn btn-ghost btn-sm" onClick={() => setOpen(true)}>
          {saved ? "Change the focus of this resume" : "Point this resume in a direction"}
        </button>
        {saved && <p className="hint tf-saved">Current focus: {saved}</p>}
      </div>
    );
  }
  return (
    <div className="tf tf-open">
      <label htmlFor="tf-text" className="tf-label">What should this resume focus on?</label>
      <textarea
        id="tf-text" rows={4} maxLength={600} value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={FOCUS_EXAMPLE}
      />
      <p className="hint">
        Riseply rewrites the resume around this. It changes what leads and how roles are worded, and drops what pulls
        the wrong way. It never adds experience you don&apos;t have, and your employers, titles and dates stay as they are.
        This uses one tailored resume.
      </p>
      <div className="tf-actions">
        <button className="btn btn-primary btn-sm" disabled={busy} onClick={go}>
          {busy ? "Re-tailoring…" : "Re-tailor with this focus"}
        </button>
        <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => { setOpen(false); setText(saved); }}>Cancel</button>
      </div>
    </div>
  );
}
