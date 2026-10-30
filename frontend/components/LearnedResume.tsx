"use client";

import { useState } from "react";
import { api, CoachCourse } from "@/lib/api";
import "./LearnedResume.css";

interface Built { label: string; base_label: string; resume_text: string; training: string[]; skills: string[]; modules: string[] }

// "Put what you've learned on your resume": a copy of the person's default
// resume with a Professional Development section and a skills line added from
// the modules they have finished. Their own text is never rewritten, and
// nothing is saved until they have read it, edited it and chosen to save.
export default function LearnedResume({ course }: { course: CoachCourse }) {
  const finished = course.modules.filter((m) => m.done);
  const [picked, setPicked] = useState<string[]>(finished.map((m) => m.id));
  const [built, setBuilt] = useState<Built | null>(null);
  const [text, setText] = useState("");
  const [label, setLabel] = useState("");
  const [makeDefault, setMakeDefault] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState("");
  const [error, setError] = useState("");

  if (finished.length === 0) return null;

  async function build() {
    if (busy || picked.length === 0) return;
    setBusy(true); setError(""); setSaved("");
    try {
      const out = await api<Built>(`/career-coach/courses/${course.id}/learned-resume`, { method: "POST", body: JSON.stringify({ module_ids: picked }) });
      setBuilt(out); setText(out.resume_text); setLabel(out.label);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't build your resume. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (saving || !text.trim() || !label.trim()) return;
    setSaving(true); setError("");
    try {
      const r = await api<{ id: number; label: string }>("/resumes", { method: "POST", body: JSON.stringify({ label: label.trim(), resume_text: text }) });
      if (makeDefault) await api(`/resumes/${r.id}/set-default`, { method: "POST" });
      setSaved(r.label);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save it. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="lr-box" aria-label="Put what you learned on your resume">
      <h3>Put what you&rsquo;ve learned on your resume</h3>
      <p className="muted">
        Makes a copy of your default resume with a &ldquo;Professional Development&rdquo; section and a skills line for the modules you pick.
        Your own text is not changed, and nothing is saved until you say so.
      </p>
      {!built && (
        <>
          <ul className="lr-mods">
            {finished.map((m) => (
              <li key={m.id}>
                <label>
                  <input type="checkbox" checked={picked.includes(m.id)}
                         onChange={(e) => setPicked(e.target.checked ? [...picked, m.id] : picked.filter((x) => x !== m.id))} />
                  <span>{m.title}</span>
                </label>
              </li>
            ))}
          </ul>
          <div className="lr-actions">
            <button className="btn btn-primary btn-sm" onClick={build} disabled={busy || picked.length === 0}>
              {busy ? "Building…" : "Build my updated resume"}
            </button>
          </div>
        </>
      )}
      {error && <p className="lr-error" role="alert">{error}</p>}
      {built && (
        <>
          <p className="lr-warn">
            Draft. It is worded as training, not job experience. Read every line and keep only what is true for you, as you would say it in an interview.
          </p>
          <p className="muted">Added from: {built.modules.join(", ")}.</p>
          <textarea className="lr-text" value={text} onChange={(e) => setText(e.target.value)} aria-label="Your updated resume" spellCheck={false} />
          <div className="lr-actions">
            <input className="lr-label" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={60} aria-label="Name for the new resume" />
          </div>
          <label style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center" }}>
            <input type="checkbox" checked={makeDefault} onChange={(e) => setMakeDefault(e.target.checked)} />
            Use it as my default resume for matching and autofill
          </label>
          <div className="lr-actions">
            {!saved && <button className="btn btn-primary btn-sm" onClick={save} disabled={saving || !text.trim() || !label.trim()}>{saving ? "Saving…" : "Save as a new resume"}</button>}
            {!saved && <button className="btn btn-ghost btn-sm" onClick={() => { setBuilt(null); setSaved(""); }}>Start over</button>}
            {saved && <span className="lr-ok">Saved as &ldquo;{saved}&rdquo;. <a href="/dashboard/resume">Open your resumes</a></span>}
          </div>
        </>
      )}
    </section>
  );
}
