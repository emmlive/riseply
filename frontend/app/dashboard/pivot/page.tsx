"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, Program, ProgramListItem, ProgramPhase } from "@/lib/api";

// A bootcamp-style route from zero to a job in a new field: ordered phases,
// each taught by the Career Coach from the ground up, then projects,
// certifications and a job-ready checklist. Quota (429) is handled globally
// by api(); other errors are shown inline.

const STATUS_LABEL: Record<string, string> = {
  not_started: "Not applying yet", applying: "Applying", interviewing: "Interviewing", offer: "Have an offer", hired: "Hired",
};
const PHASE_PILL: Record<string, string> = { done: "pill pill-approved", current: "pill pill-submitted", open: "pill pill-default", locked: "pill pill-default" };
const PHASE_WORD: Record<string, string> = { done: "Done", current: "Up next", open: "Open", locked: "Locked" };
const CERT_STATUS = [["", "Not decided"], ["planning", "Planning to take it"], ["studying", "Studying"], ["earned", "Earned"], ["skip", "Skipping it"]];

export default function PivotPage() {
  const router = useRouter();
  const [list, setList] = useState<ProgramListItem[] | null>(null);
  const [program, setProgram] = useState<Program | null>(null);
  const [role, setRole] = useState("");
  const [hours, setHours] = useState(6);
  const [background, setBackground] = useState("");
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function open(id: number) {
    try { setProgram(await api<Program>(`/career-programs/${id}`)); } catch (e: any) { setError(e.message || "Couldn't open that program."); }
  }
  useEffect(() => {
    api<ProgramListItem[]>("/career-programs").then((l) => {
      setList(l);
      if (l.length) open(l[0].id);
    }).catch(() => setList([]));
  }, []);

  async function create() {
    if (busy || role.trim().length < 2) return;
    setBusy("create"); setError("");
    try {
      const p = await api<Program>("/career-programs", { method: "POST", body: JSON.stringify({ target_role: role.trim(), hours_per_week: hours, background: background.trim() }) });
      setProgram(p); setCreating(false);
      setList(await api<ProgramListItem[]>("/career-programs"));
    } catch (e: any) { setError(e.message || "Couldn't build the program. Try again."); }
    finally { setBusy(""); }
  }

  async function put(path: string, body: object, method = "PUT") {
    if (!program) return;
    try { setProgram(await api<Program>(`/career-programs/${program.id}${path}`, { method, body: JSON.stringify(body) })); }
    catch (e: any) { setError(e.message || "Couldn't save that."); }
  }

  async function startPhase(p: ProgramPhase) {
    if (!program || busy) return;
    setBusy(p.id); setError("");
    try {
      const next = await api<Program>(`/career-programs/${program.id}/phases/${p.id}/course`, { method: "POST" });
      setProgram(next);
      const cid = next.phases.find((x) => x.id === p.id)?.course_id;
      if (cid) router.push(`/dashboard/career-coach?course=${cid}`);
    } catch (e: any) { setError(e.message || "Couldn't build this phase. Try again."); }
    finally { setBusy(""); }
  }

  async function remove() {
    if (!program || !window.confirm("Delete this program? The courses and lessons you already have stay in Career Coach.")) return;
    try {
      await api(`/career-programs/${program.id}`, { method: "DELETE" });
      const l = await api<ProgramListItem[]>("/career-programs");
      setList(l); setProgram(null);
      if (l.length) open(l[0].id);
    } catch (e: any) { setError(e.message || "Couldn't delete it."); }
  }

  if (list === null) return <p className="muted">Loading…</p>;

  const showForm = creating || (!program && list.length === 0);
  const next = program?.next_step;

  return (
    <div className="pv">
      <h1>Pivot program</h1>
      <p className="muted">
        Changing fields? Pick the role and Riseply builds a step-by-step program from zero to hired: lessons with the Career Coach,
        projects to show, certifications, then your job search. Nothing assumes you already know the field.
      </p>
      {error && <p className="cc-error" role="alert">{error}</p>}

      {list.length > 0 && !showForm && (
        <p className="pv-switch">
          {list.length > 1 && (
            <select value={program?.id ?? ""} onChange={(e) => open(Number(e.target.value))} aria-label="Program">
              {list.map((x) => <option key={x.id} value={x.id}>{x.target_role} ({x.progress}%)</option>)}
            </select>
          )}
          {list.length < 3 && <button className="btn btn-ghost btn-sm" onClick={() => setCreating(true)}>Start another program</button>}
        </p>
      )}

      {showForm && (
        <div className="card sg-form">
          <label className="cc-label" htmlFor="pv-role">The job you want</label>
          <div className="sg-row">
            <input id="pv-role" value={role} maxLength={120} onChange={(e) => setRole(e.target.value)} placeholder="e.g. Security Architect" />
          </div>
          <label className="cc-label" htmlFor="pv-bg" style={{ marginTop: 12 }}>Where you&apos;re coming from (optional)</label>
          <div className="sg-row">
            <input id="pv-bg" value={background} maxLength={200} onChange={(e) => setBackground(e.target.value)} placeholder="e.g. IT audit" />
          </div>
          <p className="hint">Used for examples that make new ideas click. It never skips a lesson.</p>
          <div className="cp-opts">
            <label>
              <span className="cc-label">Hours a week</span>
              <select value={hours} onChange={(e) => setHours(Number(e.target.value))}>
                {[3, 6, 10, 15, 20, 30].map((h) => <option key={h} value={h}>{h} hours</option>)}
              </select>
            </label>
            <button className="btn btn-primary" onClick={create} disabled={!!busy || role.trim().length < 2}>
              {busy === "create" ? "Building your program…" : "Build my program"}
            </button>
            {creating && list.length > 0 && <button className="btn btn-ghost" onClick={() => setCreating(false)}>Cancel</button>}
          </div>
        </div>
      )}

      {program && !showForm && (
        <>
          <div className="card pv-top">
            <h2>{program.title}</h2>
            {program.overview && <p>{program.overview}</p>}
            {program.role_summary && <p className="muted">{program.role_summary}</p>}
            <div className="pv-bar" role="progressbar" aria-valuenow={program.progress} aria-valuemin={0} aria-valuemax={100} aria-label="Program progress">
              <span style={{ width: `${program.progress}%` }} />
            </div>
            <p className="pv-meta">
              <strong>{program.progress}% done.</strong>{" "}
              {program.weeks_left > 0 ? `About ${program.weeks_left} weeks of lessons left at ${program.hours_per_week} hours a week.` : "All lessons finished."}
            </p>
            <div className="pv-row">
              <label>
                <span className="cc-label">Hours a week</span>
                <select value={program.hours_per_week} onChange={(e) => put("", { hours_per_week: Number(e.target.value) }, "PATCH")}>
                  {[3, 6, 10, 15, 20, 30].map((h) => <option key={h} value={h}>{h} hours</option>)}
                </select>
              </label>
              <label>
                <span className="cc-label">Job search</span>
                <select value={program.status} onChange={(e) => put("", { status: e.target.value }, "PATCH")}>
                  {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
            </div>
            {program.honest_note && <p className="muted sg-basis">{program.honest_note}</p>}
          </div>

          {next && (
            <div className="card pv-next">
              <h2>Up next</h2>
              <p><strong>{next.text}</strong>{next.minutes ? <span className="muted"> · {next.minutes} min</span> : null}</p>
              {next.kind === "build_phase" && (
                <button className="btn btn-primary" onClick={() => startPhase(program.phases.find((p) => p.id === next.phase_id)!)} disabled={!!busy}>
                  {busy === next.phase_id ? "Building your lessons…" : "Start this phase"}
                </button>
              )}
              {next.kind === "module" && <Link className="btn btn-primary" href={`/dashboard/career-coach?course=${next.course_id}`}>Go to your lesson</Link>}
              {["projects", "certs", "job_ready"].includes(next.kind) && (
                <a className="btn btn-primary" href={`#phase-${next.phase_id}`}>Go there</a>
              )}
            </div>
          )}

          {program.week_plan.lessons.length > 0 && (
            <div className="card">
              <h2>This week</h2>
              <p className="muted">What fits in your {program.week_plan.hours} hours, in order.</p>
              <ol className="pv-week">
                {program.week_plan.lessons.map((l) => (
                  <li key={l.module_id}><Link href={`/dashboard/career-coach?course=${l.course_id}`}>{l.title}</Link> <span className="muted">· {l.minutes} min</span></li>
                ))}
              </ol>
            </div>
          )}

          <h2 className="pv-h">Your roadmap</h2>
          {program.phases.map((p) => (
            <div className={`card pv-phase pv-${p.status}`} key={p.id} id={`phase-${p.id}`}>
              <div className="pv-phase-head">
                <h3>{p.name}{p.optional ? " (optional)" : ""}</h3>
                <span className={PHASE_PILL[p.status]}>{PHASE_WORD[p.status]}</span>
              </div>
              <p>{p.goal}</p>

              {["foundations", "core", "advanced"].includes(p.kind) && (
                <>
                  {p.skills && p.skills.length > 0 && <p className="muted">You will learn: {p.skills.join(", ")}.</p>}
                  {p.modules && p.modules.length > 0 ? (
                    <ul className="pv-mods">
                      {p.modules.map((m) => <li key={m.id} className={m.done ? "pv-done" : ""}>{m.done ? "✓ " : "○ "}{m.title} <span className="muted">· {m.minutes} min</span></li>)}
                    </ul>
                  ) : p.weeks ? <p className="muted">About {p.weeks} weeks. Your lessons are built when you start.</p> : null}
                  {p.status !== "locked" && !p.complete && (
                    p.course_id
                      ? <Link className="btn btn-primary btn-sm" href={`/dashboard/career-coach?course=${p.course_id}`}>Open lessons</Link>
                      : <button className="btn btn-primary btn-sm" onClick={() => startPhase(p)} disabled={!!busy}>{busy === p.id ? "Building…" : "Start this phase"}</button>
                  )}
                  {p.status === "locked" && <p className="muted">Finish the phase before this one first. Each builds on the last.</p>}
                </>
              )}

              {p.kind === "projects" && (p.status === "locked"
                ? <p className="muted">Opens when you finish the first two phases.</p>
                : <ul className="pv-items">
                    {(p.items || []).map((it, i) => (
                      <li key={i}>
                        <label className="pv-check">
                          <input type="checkbox" checked={!!it.done} onChange={(e) => put(`/projects/${i}`, { done: e.target.checked, url: it.url || "", note: it.note || "" })} />
                          <span><strong>{it.title}</strong><br />{it.build}<br /><span className="muted">Show: {it.deliverable}</span></span>
                        </label>
                        <input className="pv-url" defaultValue={it.url || ""} placeholder="Link to your work (GitHub, write-up…)" maxLength={300}
                               onBlur={(e) => { if ((e.target.value || "") !== (it.url || "")) put(`/projects/${i}`, { done: !!it.done, url: e.target.value, note: it.note || "" }); }} />
                      </li>
                    ))}
                  </ul>)}

              {p.kind === "certs" && (p.status === "locked"
                ? <p className="muted">Opens when you finish the first two phases.</p>
                : <>
                    <ul className="pv-items">
                      {(p.items || []).map((it, i) => (
                        <li key={i} className="pv-cert">
                          <span><strong>{it.name}</strong><br /><span className="muted">{it.why}</span></span>
                          <select value={it.status || ""} onChange={(e) => put(`/certs/${i}`, { status: e.target.value })} aria-label={`Status for ${it.name}`}>
                            {CERT_STATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                          </select>
                        </li>
                      ))}
                    </ul>
                    <p className="hint">Check each certification&apos;s official site for current requirements and costs. Passing one is never a promise of a job.</p>
                    <Link className="btn btn-ghost btn-sm" href={`/dashboard/exam-prep?exam=${encodeURIComponent(p.items?.[0]?.name || program.target_role)}`}>Study with Exam prep</Link>
                  </>)}

              {p.kind === "job_ready" && (p.status === "locked"
                ? <p className="muted">Opens when you finish the first two phases, so you can start applying before everything else is done.</p>
                : <ul className="pv-items">
                    {(p.items || []).map((it) => (
                      <li key={it.id}>
                        <label className="pv-check">
                          <input type="checkbox" checked={!!it.done} onChange={(e) => put(`/checklist/${it.id}`, { done: e.target.checked })} />
                          <span>{it.text}</span>
                        </label>
                        {it.href && <Link className="btn btn-ghost btn-sm" href={it.href}>{it.label}</Link>}
                      </li>
                    ))}
                  </ul>)}
            </div>
          ))}

          <p className="muted" style={{ fontSize: "0.82rem" }}><button className="sg-link" onClick={remove}>Delete this program</button></p>
        </>
      )}
    </div>
  );
}
