"use client";

import { useState } from "react";
import Link from "next/link";
import { api, CoachRecap, StudyNote } from "@/lib/api";

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
  const [saved, setSaved] = useState(false);
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
      <p className="mr-summary">{recap.summary}</p>

      <h4>Remember</h4>
      <ul className="mr-points">{recap.key_points.map((p) => <li key={p}>{p}</li>)}</ul>

      {recap.terms.length > 0 && (
        <>
          <h4>Terms</h4>
          <dl className="mr-terms">
            {recap.terms.map((t) => (<div key={t.term}><dt>{t.term}</dt><dd>{t.meaning}</dd></div>))}
          </dl>
        </>
      )}

      {recap.example && (<><h4>Example</h4><p>{recap.example}</p></>)}
      {recap.shaky.length > 0 && (<><h4>Look at again</h4><ul className="mr-points">{recap.shaky.map((p) => <li key={p}>{p}</li>)}</ul></>)}
      {recap.practice && (<p className="mr-practice"><strong>Before the next module:</strong> {recap.practice}</p>)}
      {recap.next_up && <p className="muted mr-next">{recap.next_up}</p>}

      <div className="mr-actions">
        <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>
          {saving ? "Saving…" : saved ? "Saved. Save again to update" : "Save recap to study folder"}
        </button>
        {onNext && <button className="btn btn-ghost btn-sm" onClick={onNext}>{nextLabel || "Next module"}</button>}
        {saved && <Link href="/dashboard/career-coach/study" className="mr-link">Open study folders</Link>}
      </div>
      {error && <p className="cc-error" role="alert" style={{ marginTop: 8 }}>{error}</p>}
    </section>
  );
}
