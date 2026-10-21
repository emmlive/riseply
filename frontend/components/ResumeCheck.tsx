"use client";

import { useState } from "react";
import { api, type ResumeCheck as Check } from "@/lib/api";

// "Will it get through screening?" Shows which of the posting's key words and
// hard requirements the tailored resume covers (free, no AI), and lets the
// person add real experience the resume leaves out, which the next re-tailor
// may then use. The person is the source of every fact they add.
export default function ResumeCheck({ applicationId, onRetailor, busy }: {
  applicationId: number; onRetailor: () => Promise<void>; busy: boolean;
}) {
  const [data, setData] = useState<Check | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [adding, setAdding] = useState<string | null>(null);
  const [detail, setDetail] = useState("");
  const [saved, setSaved] = useState(false);

  async function load() {
    setLoading(true); setError("");
    try {
      setData(await api<Check>(`/applications/${applicationId}/resume-check`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't check this resume. Try again.");
    } finally {
      setLoading(false);
    }
  }

  async function addFact() {
    if (!adding || detail.trim().length < 8) return;
    setError("");
    try {
      await api("/resume-facts", { method: "POST", body: JSON.stringify({ skill: adding, detail: detail.trim() }) });
      setAdding(null); setDetail(""); setSaved(true);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't save. Try again.");
    }
  }

  async function removeFact(id: number) {
    try {
      await api(`/resume-facts/${id}`, { method: "DELETE" });
      setSaved(true);
      await load();
    } catch { /* leave the list as it is */ }
  }

  async function retailor() {
    await onRetailor();
    setSaved(false);
    await load();
  }

  return (
    <div className="rc" style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
      {!data && (
        <>
          <button className="btn btn-ghost btn-sm" disabled={loading} onClick={load}>
            {loading ? "Checking…" : "Will it get through screening?"}
          </button>
          {error && <p className="cc-error" role="alert" style={{ marginTop: 8 }}>{error}</p>}
        </>
      )}
      {data && (
        <>
          <h3 style={{ fontSize: "0.95rem", marginBottom: 6 }}>Will it get through screening?</h3>
          {data.ready && (
            <div className="rc-ready" aria-label={`ATS readiness ${data.ready.score} out of 100, ${data.ready.label}`}>
              <div className={`rc-score ${data.ready.score >= 80 ? "good" : data.ready.score >= 60 ? "fair" : "low"}`}>
                <span className="rc-num">{data.ready.score}</span><span className="rc-of">/100</span>
              </div>
              <div className="rc-ready-body">
                <strong>ATS readiness: {data.ready.label}</strong>
                <ul className="rc-parts">
                  {data.ready.parts.filter((p) => p.score !== null).map((p) => (
                    <li key={p.name}>
                      <span>{p.name}</span>
                      <span className="rc-bar" aria-hidden><i style={{ width: `${p.score}%` }} /></span>
                      <span className="muted">{p.score}</span>
                    </li>
                  ))}
                </ul>
                <p className="hint" style={{ margin: "4px 0 0" }}>{data.ready.next}</p>
              </div>
            </div>
          )}
          <p style={{ margin: "0 0 8px" }}>
            <strong>{data.found} of {data.total}</strong> key words from this posting are on your tailored resume
            {data.found_before < data.found ? <span className="muted"> (your original had {data.found_before})</span> : null}.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {data.terms.map((t) => t.in_tailored ? (
              <span key={t.term} className="pill pill-approved">✓ {t.term}</span>
            ) : (
              <button key={t.term} type="button" className="pill pill-rejected rc-miss" onClick={() => { setAdding(t.term); setDetail(""); }}
                      aria-label={`${t.term} is not on your resume. Add experience with it.`}>✗ {t.term}</button>
            ))}
          </div>
          {data.terms.some((t) => !t.in_tailored) && !adding && (
            <p className="hint" style={{ margin: "8px 0 0" }}>
              Missing one you really have? Tap it and say what you did. Only add what you could talk about in an interview.
            </p>
          )}

          {adding && (
            <div className="rc-add">
              <label htmlFor={`rc-${applicationId}`}>What have you done with <strong>{adding}</strong>? One sentence, in your words.</label>
              <textarea id={`rc-${applicationId}`} rows={2} maxLength={240} value={detail} onChange={(e) => setDetail(e.target.value)}
                        placeholder="For example: built a monthly controls dashboard that cut review time in half" />
              <div className="rc-row">
                <button className="btn btn-primary btn-sm" disabled={detail.trim().length < 8} onClick={addFact}>Add to my experience</button>
                <button className="btn btn-ghost btn-sm" onClick={() => { setAdding(null); setDetail(""); }}>Cancel</button>
              </div>
            </div>
          )}

          {data.checks.length > 0 && (
            <>
              <h4 className="brief-h" style={{ marginTop: 14 }}>Requirements a screen may filter on</h4>
              <ul className="brief-list">
                {data.checks.map((c) => (
                  <li key={c.label}><span aria-hidden>{c.ok ? "✓" : "⚠"}</span> <strong>{c.label}.</strong> {c.detail}</li>
                ))}
              </ul>
            </>
          )}

          {data.facts.length > 0 && (
            <>
              <h4 className="brief-h" style={{ marginTop: 14 }}>Experience you added</h4>
              <ul className="brief-list">
                {data.facts.map((f) => (
                  <li key={f.id}>
                    <strong>{f.skill}:</strong> {f.detail}{" "}
                    <button className="sg-link" onClick={() => removeFact(f.id)} aria-label={`Remove ${f.skill}`}>Remove</button>
                  </li>
                ))}
              </ul>
            </>
          )}

          {saved && (
            <div className="rc-row" style={{ marginTop: 10 }}>
              <button className="btn btn-primary btn-sm" disabled={busy} onClick={retailor}>
                {busy ? "Re-tailoring…" : "Re-tailor with this"}
              </button>
              <span className="hint">Uses one tailoring from your plan.</span>
            </div>
          )}
          {error && <p className="cc-error" role="alert" style={{ marginTop: 8 }}>{error}</p>}
          <p className="hint" style={{ margin: "10px 0 0" }}>
            An estimate of how a keyword and requirements screen would treat this resume, not a prediction for any one employer&apos;s system.
          </p>
        </>
      )}
    </div>
  );
}
