"use client";

import { useState } from "react";
import Link from "next/link";
import { api, CoachRecap, StudyNote } from "@/lib/api";
import StudyNoteBody from "@/components/StudyNoteBody";
import { printNote, recapToMarkdown } from "@/lib/noteFormat";

// The end-of-module recap: what the module covered, what to remember, the
// vocabulary, one practice task. One press files it in a study folder named
// after the course.
export default function ModuleRecap({ recap, sessionId, moduleLabel, onNext, nextLabel }: {
  recap: CoachRecap;
  sessionId: number;
  moduleLabel: string;
  onNext?: () => void;
  nextLabel?: string;
}) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(!!recap.filed);
  const [error, setError] = useState("");

  async function save() {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      await api<StudyNote>(`/career-coach/courses/sessions/${sessionId}/save-recap`, { method: "POST" });
      setSaved(true);
    } catch (e: any) {
      setError(e.message || "Couldn't save the recap. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="mr-card" aria-label={`Recap: ${moduleLabel}`}>
      <header className="mr-head">
        <h3>Recap</h3>
        <span className="muted">{moduleLabel}</span>
      </header>
      <div className="mr-body"><StudyNoteBody text={recapToMarkdown(recap)} /></div>

      <div className="mr-actions">
        <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>
          {saving ? "Saving…" : saved ? "Saved to your study folder. Update" : "Save notes to study folder"}
        </button>
        {onNext && <button className="btn btn-ghost btn-sm" onClick={onNext}>{nextLabel || "Next module"}</button>}
        <button className="btn btn-ghost btn-sm" onClick={() => printNote(`${moduleLabel} notes`, recapToMarkdown(recap))}>Print or save as PDF</button>
        {saved && <Link href="/dashboard/career-coach/study" className="mr-link">Open study folders</Link>}
      </div>
      {error && <p className="cc-error" role="alert" style={{ marginTop: 8 }}>{error}</p>}
    </section>
  );
}
