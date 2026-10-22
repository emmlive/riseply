"use client";

import { useRef, useState } from "react";
import { api, TaskGuide } from "@/lib/api";

const VERDICT: Record<string, { label: string; cls: string }> = {
  ready: { label: "Ready to hand in", cls: "dr-ready" },
  almost: { label: "Almost there", cls: "dr-almost" },
  not_yet: { label: "Not ready yet", cls: "dr-not" },
};
const PRIORITY: Record<string, string> = { high: "Fix first", medium: "Should fix", low: "Polish" };

// "Check my draft": attach a document, spreadsheet, PDF or text file (or paste
// the text) and get it checked against this guide's requirements. The latest
// review is saved with the guide.
export default function DraftReview({ guide, onUpdated }: { guide: TaskGuide; onUpdated: (g: TaskGuide) => void }) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileEl = useRef<HTMLInputElement>(null);
  const r = guide.review;

  async function run() {
    if (busy || (!file && text.trim().length < 40)) return;
    setBusy(true);
    setError("");
    try {
      const fd = new FormData();
      if (file) fd.append("file", file);
      else fd.append("text", text);
      const g = await api<TaskGuide>(`/task-guides/${guide.id}/review`, { method: "POST", body: fd });
      onUpdated(g);
      setFile(null);
      setText("");
      if (fileEl.current) fileEl.current.value = "";
    } catch (e: any) {
      setError(e.message || "Couldn't review your draft. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card dr-card">
      <h3 style={{ marginTop: 0 }}>Check your draft</h3>
      <p className="muted" style={{ marginTop: 0 }}>
        Attach what you have so far, or paste it. The guide checks it against the requirements above, says what is missing and what to fix first.
        It does not rewrite your work.
      </p>
      <div className="dr-input">
        <label className="btn btn-ghost btn-sm dr-attach">
          📎 {file ? "Change file" : "Attach a file"}
          <input ref={fileEl} type="file" hidden accept=".docx,.xlsx,.xlsm,.pdf,.txt,.md,.csv"
                 onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        <span className="muted dr-hint">Word, Excel, PDF, text or CSV, up to 3 MB.</span>
      </div>
      {file ? (
        <p className="dr-file">
          <strong>{file.name}</strong>{" "}
          <button className="sg-link" onClick={() => { setFile(null); if (fileEl.current) fileEl.current.value = ""; }}>Remove</button>
        </p>
      ) : (
        <textarea className="cc-input" rows={6} value={text} maxLength={24000} onChange={(e) => setText(e.target.value)}
                  placeholder="Or paste your draft here." aria-label="Your draft" />
      )}
      {error && <p className="cc-error" role="alert">{error}</p>}
      <div style={{ marginTop: 10 }}>
        <button className="btn btn-primary btn-sm" onClick={run} disabled={busy || (!file && text.trim().length < 40)}>
          {busy ? "Reviewing…" : r ? "Review again" : "Review my draft"}
        </button>
      </div>

      {r && (
        <div className="dr-result" aria-live="polite">
          <div className="dr-head">
            <span className={`dr-badge ${VERDICT[r.verdict]?.cls ?? "dr-almost"}`}>{VERDICT[r.verdict]?.label ?? r.verdict}</span>
            <span className="muted">{r.source}{r.reviewed_at ? ` · ${new Date(r.reviewed_at + "Z").toLocaleString()}` : ""}</span>
          </div>
          <p>{r.summary}</p>
          {r.gaps.length > 0 && (
            <>
              <h4>What to fix</h4>
              <ul className="dr-gaps">
                {r.gaps.map((g, i) => (
                  <li key={i}>
                    <span className={`dr-pri dr-pri-${g.priority}`}>{PRIORITY[g.priority] ?? g.priority}</span>
                    <strong>{g.item}</strong>
                    {g.fix && <div>{g.fix}</div>}
                  </li>
                ))}
              </ul>
            </>
          )}
          {r.meets.length > 0 && (
            <>
              <h4>What is already good</h4>
              <ul className="tg-list">{r.meets.map((m, i) => <li key={i}><strong>{m.item}</strong>{m.note ? `: ${m.note}` : ""}</li>)}</ul>
            </>
          )}
          {r.next_step && <p className="dr-next"><strong>Next:</strong> {r.next_step}</p>}
        </div>
      )}
    </div>
  );
}
