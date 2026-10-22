"use client";

import { useRef, useState } from "react";
import { Attached, shrinkImage } from "@/lib/images";

// Where a person hands in a hands-on task: a roomy text box for the answer
// (a policy, a query, an email, notes) and up to two pictures (a photo of a
// drawing, a screenshot). The coach reads both and gives feedback.
export default function WorkArea({ onSend, disabled }: {
  onSend: (text: string, images: { media_type: string; data: string }[]) => void;
  disabled?: boolean;
}) {
  const [text, setText] = useState("");
  const [pics, setPics] = useState<Attached[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const fileEl = useRef<HTMLInputElement>(null);

  async function add(files: FileList | null) {
    if (!files?.length) return;
    setError("");
    setBusy(true);
    try {
      const next = [...pics];
      for (const f of Array.from(files)) {
        if (next.length >= 2) { setError("You can attach up to two pictures."); break; }
        next.push(await shrinkImage(f));
      }
      setPics(next);
    } catch (e: any) {
      setError(e.message || "Couldn't attach that picture.");
    } finally {
      setBusy(false);
      if (fileEl.current) fileEl.current.value = "";
    }
  }

  const ready = (text.trim().length > 0 || pics.length > 0) && !disabled && !busy;
  return (
    <div className="dp">
      <label className="dp-field">
        <span>Your work for this task</span>
        <textarea className="cc-input" rows={10} value={text} maxLength={12000} onChange={(e) => setText(e.target.value)}
                  placeholder="Write or paste your answer here: a policy, a query, an email, a plan, your notes." />
      </label>
      <div className="wa-pics">
        {pics.map((p, i) => (
          <figure key={i} className="wa-pic">
            <img src={p.preview} alt={`Attached picture ${i + 1}`} />
            <button className="btn btn-ghost btn-sm" onClick={() => setPics(pics.filter((_, j) => j !== i))}>Remove</button>
          </figure>
        ))}
        {pics.length < 2 && (
          <label className="btn btn-ghost btn-sm wa-attach">
            {busy ? "Adding…" : "📎 Attach a picture"}
            <input ref={fileEl} type="file" accept="image/*" multiple hidden onChange={(e) => add(e.target.files)} />
          </label>
        )}
      </div>
      <p className="muted dp-hint">A photo of paper, a screenshot or a drawing from another tool all work. Pictures are shrunk before they are sent and only used for this reply.</p>
      {error && <p className="cc-error" role="alert">{error}</p>}
      <div className="dp-actions">
        <button className="btn btn-primary btn-sm" disabled={!ready}
                onClick={() => onSend(text.trim() ? `Here is my work for the task:\n\n${text.trim()}` : "Here is my work for the task (see the attached picture).", pics.map(({ media_type, data }) => ({ media_type, data })))}>
          Send my work to the coach
        </button>
      </div>
    </div>
  );
}
