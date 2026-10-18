"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, formatWhen, SkillGapItem, SkillGapReport } from "@/lib/api";

// "What am I missing for the role I want?" Compares the person's resume with a
// target role and the real listings Riseply has found for it, then sends each
// gap straight into a hands-on Career Coach session. Quota (429) is handled
// globally by api(); other errors are shown inline.

const IMPORTANCE_LABEL: Record<SkillGapItem["importance"], string> = {
  high: "Worth doing first",
  medium: "Next up",
  low: "Nice to have",
};

function practiceLink(role: string, gap: SkillGapItem): string {
  const topic = gap.tool ? `${gap.skill} using ${gap.tool}` : gap.skill;
  const q = new URLSearchParams({ role, topic, type: "upskill", style: "handson" });
  return `/dashboard/career-coach?${q.toString()}`;
}

export default function SkillGapPage() {
  const [role, setRole] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [report, setReport] = useState<SkillGapReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const sugg = api<string[]>("/skill-gap/suggestions").catch(() => [] as string[]);
    sugg.then(setSuggestions);
    api<SkillGapReport[]>("/skill-gap/latest")
      .then(async (rows) => {
        if (rows.length) { setReport(rows[0]); setRole(rows[0].target_role); }
        else { const s = await sugg; if (s[0]) setRole((cur) => cur || s[0]); }
      })
      .catch(() => {});
  }, []);

  async function run(refresh = false) {
    if (busy || role.trim().length < 2) return;
    setBusy(true);
    setError("");
    try {
      setReport(await api<SkillGapReport>("/skill-gap", { method: "POST", body: JSON.stringify({ target_role: role.trim(), refresh }) }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>Skill gaps</h1>
      <p className="muted">
        See what your resume already shows for the role you want, what it&apos;s missing, and how to start building each
        gap with the Career Coach. It compares your default resume with real listings we&apos;ve found.
      </p>

      <div className="card sg-form">
        <label className="cc-label" htmlFor="sg-role">Role you&apos;re aiming for</label>
        <div className="sg-row">
          <input
            id="sg-role" list="sg-roles" value={role} maxLength={120}
            onChange={(e) => setRole(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") run(); }}
            placeholder="e.g. Vulnerability Analyst"
          />
          <datalist id="sg-roles">{suggestions.map((s) => <option key={s} value={s} />)}</datalist>
          <button className="btn btn-primary" onClick={() => run()} disabled={busy || role.trim().length < 2}>
            {busy ? "Analyzing…" : "Find my gaps"}
          </button>
        </div>
        {error && <p className="cc-error" role="alert">{error}</p>}
      </div>

      {report && (
        <>
          <div className="card sg-summary">
            <h2>{report.target_role}</h2>
            <p>{report.summary}</p>
            {report.next_step && <p className="sg-next"><strong>Start here:</strong> {report.next_step}</p>}
            <p className="muted sg-basis">
              {report.jobs_used > 0
                ? `Based on ${report.jobs_used} real listing${report.jobs_used === 1 ? "" : "s"} and your resume.`
                : "We haven't found listings for this role yet, so this reflects what the role usually asks for."}{" "}
              {report.cached ? `Saved ${formatWhen(report.created_at)}. ` : ""}
              <button className="sg-link" onClick={() => run(true)} disabled={busy}>Re-run</button>
            </p>
          </div>

          {report.strengths.length > 0 && (
            <>
              <h2>Already on your resume</h2>
              <ul className="sg-strengths">
                {report.strengths.map((s) => (
                  <li key={s.skill}><strong>{s.skill}</strong>{s.evidence && <span className="muted"> — {s.evidence}</span>}</li>
                ))}
              </ul>
            </>
          )}

          <h2>Gaps to close</h2>
          {report.gaps.length === 0 && <div className="empty-state">No clear gaps found. Your resume covers what this role usually asks for.</div>}
          {report.gaps.map((g) => (
            <div className={`card sg-gap sg-${g.importance}`} key={g.skill}>
              <div className="sg-gap-head">
                <h3>{g.skill}</h3>
                <span className="sg-badge">{IMPORTANCE_LABEL[g.importance]}</span>
              </div>
              {report.jobs_used > 0 && (
                <div className="sg-seen" aria-label={`In ${g.seen_in} of ${report.jobs_used} listings`}>
                  <div className="sg-track"><div className="sg-fill" style={{ width: `${Math.round((g.seen_in / report.jobs_used) * 100)}%` }} /></div>
                  <span className="muted">In {g.seen_in} of {report.jobs_used} listings</span>
                </div>
              )}
              {g.why && <p>{g.why}</p>}
              {g.first_exercise && (
                <p className="sg-ex"><strong>First step{g.tool ? ` (${g.tool})` : ""}:</strong> {g.first_exercise}</p>
              )}
              <Link className="btn btn-ghost btn-sm" href={practiceLink(report.target_role, g)}>Practice this with the coach</Link>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
