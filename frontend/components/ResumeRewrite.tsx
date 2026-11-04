"use client";

import { useState } from "react";
import { api, SavedResume } from "@/lib/api";
import ResumeDownload from "./ResumeDownload";
import "./ResumeRewrite.css";

interface Draft { label: string; base_label: string; resume_text: string }

export const REWRITE_EXAMPLE = "Security Architect. Keep every role focused on security architecture, governance and compliance. Don't make me look like a developer.";

// Write a new version of one of your resumes, pointed the way you ask. It
// never adds experience you don't have. You read and edit the draft, name it,
// and save it as a new resume next to the others.
export default function ResumeRewrite({ resumes, onSaved }: { resumes: SavedResume[]; onSaved: () => Promise<void> | void }) {
  const def = resumes.find((r) => r.is_default) || resumes[0];
  const [baseId, setBaseId] = useState("");
  const [focus, setFocus] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [text, setText] = useState("");
  const [label, setLabel] = useState("");
  const [makeDefault, setMakeDefault] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState("");
  const [error, setError] = useState("");

  if (!def) return null;

  async function write() {
    if (busy || focus.trim().length < 8) return;
    setBusy(true); setError(""); setSaved("");
    try {
      const out = await api<Draft>("/resumes/rewrite", {
        method: "POST",
        body: JSON.stringify({ focus: focus.trim(), resume_id: baseId ? Number(baseId) : null }),
      });
      setDraft(out); setText(out.resume_text); setLabel(out.label);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't write your resume. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (saving || !text.trim() || !label.trim()) return;
    setSaving(true); setError("");
    try {
      const r = await api<SavedResume>("/resumes", { method: "POST", body: JSON.stringify({ label: label.trim(), resume_text: text }) });
      if (makeDefault) await api(`/resumes/${r.id}/set-default`, { method: "POST" });
      setSaved(r.label);
      await onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save it. Try again.");
    } finally {
      setSaving(false);
    }
  }

  function again() { setDraft(null); setSaved(""); setError(""); }

  return (
    <section className="rr-box" aria-label="Write a new version of your resume">
      <h3>Write a new version of your resume</h3>
      {!draft && (
        <>
          <p className="muted">
            Tell Riseply what the new resume should focus on. It rewrites a copy of the resume you pick, leading with the
            experience that fits and leaving out what pulls the other way. It never adds experience you don&rsquo;t have,
            and your employers, titles and dates stay as they are. Nothing is saved until you say so.
          </p>
          {resumes.length > 1 && (
            <>
              <label htmlFor="rr-base" className="rr-label">Start from which resume?</label>
              <select id="rr-base" value={baseId} onChange={(e) => setBaseId(e.target.value)} className="rr-select">
                <option value="">{def.label || "My default resume"} (default)</option>
                {resumes.filter((r) => r.id !== def.id).map((r) => <option key={r.id} value={r.id}>{r.label || "Untitled resume"}</option>)}
              </select>
            </>
          )}
          <label htmlFor="rr-focus" className="rr-label">What should it focus on?</label>
          <textarea id="rr-focus" className="rr-focus" rows={3} maxLength={600} value={focus}
                    onChange={(e) => setFocus(e.target.value)} placeholder={REWRITE_EXAMPLE} />
          <div className="rr-actions">
            <button className="btn btn-primary btn-sm" onClick={write} disabled={busy || focus.trim().length < 8}>
              {busy ? "Writing…" : "Write my new resume"}
            </button>
          </div>
        </>
      )}
      {error && <p className="rr-error" role="alert">{error}</p>}
      {draft && (
        <>
          <p className="rr-warn">
            Draft, rewritten from &ldquo;{draft.base_label}&rdquo;. Read every line and fix anything that isn&rsquo;t right for you before you save it.
          </p>
          <textarea className="rr-text" value={text} onChange={(e) => setText(e.target.value)} aria-label="Your new resume" spellCheck={false} />
          <p className="hint" style={{ margin: "6px 0 0" }}>Edit the text above if you like. Downloads include your edits.</p>
          <div style={{ marginTop: 8 }}><ResumeDownload text={text} name={label} /></div>
          <label htmlFor="rr-name" className="rr-label">Name for this resume</label>
          <input id="rr-name" className="rr-name" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={60} />
          <label className="rr-check">
            <input type="checkbox" checked={makeDefault} onChange={(e) => setMakeDefault(e.target.checked)} />
            Use it as my default resume for matching and autofill
          </label>
          <div className="rr-actions">
            {!saved && <button className="btn btn-primary btn-sm" onClick={save} disabled={saving || !text.trim() || !label.trim()}>{saving ? "Saving…" : "Save as a new resume"}</button>}
            {!saved && <button className="btn btn-ghost btn-sm" onClick={again}>Start over</button>}
            {saved && <span className="rr-ok">Saved as &ldquo;{saved}&rdquo;. It is in your list of resumes above.</span>}
            {saved && <button className="btn btn-ghost btn-sm" onClick={() => { again(); setFocus(""); }}>Write another</button>}
          </div>
        </>
      )}
    </section>
  );
}
