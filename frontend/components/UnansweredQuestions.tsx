"use client";

import { useEffect, useState } from "react";
import { api, AutofillProfile } from "@/lib/api";

export interface UnansweredQuestion { id: number; question: string; host: string; times_seen: number; last_seen: string | null }

// Questions Autofill came across on application forms and had no answer for.
// Answer one here and it becomes a saved answer, filled in next time.
export default function UnansweredQuestions({ onSaved }: { onSaved: (p: AutofillProfile) => void }) {
  const [rows, setRows] = useState<UnansweredQuestion[]>([]);
  const [text, setText] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState("");

  function load() {
    api<{ questions: UnansweredQuestion[] }>("/autofill-profile/unanswered").then((r) => setRows(r.questions)).catch(() => {});
  }
  useEffect(load, []);

  async function save(q: UnansweredQuestion) {
    setBusy(q.id); setError("");
    try {
      const r = await api<{ profile: AutofillProfile }>(`/autofill-profile/unanswered/${q.id}/answer`, { method: "POST", body: JSON.stringify({ answer: text[q.id] || "" }) });
      onSaved(r.profile);
      setRows((x) => x.filter((y) => y.id !== q.id));
    } catch (e: any) { setError(e?.message || "Couldn't save that answer."); }
    finally { setBusy(null); }
  }

  async function dismiss(q: UnansweredQuestion) {
    setBusy(q.id); setError("");
    try {
      await api(`/autofill-profile/unanswered/${q.id}/dismiss`, { method: "POST" });
      setRows((x) => x.filter((y) => y.id !== q.id));
    } catch (e: any) { setError(e?.message || "Couldn't dismiss that."); }
    finally { setBusy(null); }
  }

  if (!rows.length) return null;
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h2 style={{ marginTop: 0 }}>Questions Autofill couldn&apos;t answer</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        These came up on application forms and had no answer in your profile. Answer one here and Autofill uses it next time.
        Riseply also counts which questions come up most, without names, to learn what to support next.
      </p>
      {rows.map((q) => (
        <div key={q.id} className="af-item" style={{ borderTop: "1px solid var(--border)", paddingTop: 12, marginTop: 12 }}>
          <strong>{q.question}</strong>
          <div className="hint">{q.host ? `Seen on ${q.host}` : "Seen on an application form"}{q.times_seen > 1 ? ` · ${q.times_seen} times` : ""}</div>
          <textarea rows={2} value={text[q.id] || ""} placeholder="Your answer, in your own words" onChange={(e) => setText({ ...text, [q.id]: e.target.value })} style={{ width: "100%", marginTop: 6 }} />
          <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
            <button className="btn btn-primary btn-sm" disabled={busy === q.id || !(text[q.id] || "").trim()} onClick={() => save(q)}>Save as an answer</button>
            <button className="btn btn-ghost btn-sm" disabled={busy === q.id} onClick={() => dismiss(q)}>Not for me</button>
          </div>
        </div>
      ))}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
