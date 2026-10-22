"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, formatWhen, CareerPath, CoachCourse } from "@/lib/api";

// "How do I get from here to that role?" A staged plan built from the
// person's resume. Each skill opens a hands-on Career Coach session. Quota
// (429) is handled globally by api(); other errors are shown inline.

const FIT_LABEL: Record<string, string> = {
  close: "Close: mostly positioning and a few skills",
  stretch: "A stretch: real new skills, doable in your time",
  long_haul: "A long haul: a bigger change than this time allows",
};

function practiceLink(role: string, skill: string): string {
  const q = new URLSearchParams({ role, topic: skill, type: "upskill", style: "handson" });
  return `/dashboard/career-coach?${q.toString()}`;
}

// One coach session for a whole stage: the stage and its skills are the topic.
function stageLink(role: string, stage: { name: string; skills: string[] }): string {
  const topic = `${stage.name}: ${stage.skills.join(", ")}`.slice(0, 200);
  const q = new URLSearchParams({ role, topic, type: "upskill", style: "handson" });
  return `/dashboard/career-coach?${q.toString()}`;
}

export default function CareerPathPage() {
  const [role, setRole] = useState("");
  const [months, setMonths] = useState(12);
  const [hours, setHours] = useState(5);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [plan, setPlan] = useState<CareerPath | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();
  const [courseBusy, setCourseBusy] = useState("");

  // Build a syllabus for a stage and open it in the Career Coach.
  async function teachAsCourse(s: { name: string; skills: string[] }) {
    if (!plan || courseBusy) return;
    setCourseBusy(s.name);
    setError("");
    try {
      const c = await api<CoachCourse>("/career-coach/courses", {
        method: "POST",
        body: JSON.stringify({ target_role: plan.target_role, topic: s.name.slice(0, 200), skills: s.skills.slice(0, 8) }),
      });
      router.push(`/dashboard/career-coach?course=${c.id}`);
    } catch (e: any) {
      setError(e.message || "Couldn't build the course. Try again.");
      setCourseBusy("");
    }
  }

  useEffect(() => {
    api<string[]>("/skill-gap/suggestions").then(setSuggestions).catch(() => {});
    api<CareerPath | null>("/career-path/latest")
      .then((p) => {
        if (p) { setPlan(p); setRole(p.target_role); setMonths(p.months); setHours(p.hours_per_week); }
      })
      .catch(() => {});
  }, []);

  async function build(refresh = false) {
    if (busy || role.trim().length < 2) return;
    setBusy(true);
    setError("");
    try {
      setPlan(await api<CareerPath>("/career-path", {
        method: "POST",
        body: JSON.stringify({ target_role: role.trim(), months, hours_per_week: hours, refresh }),
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>Career path</h1>
      <p className="muted">
        Pick the role you want and how much time you can give. You&apos;ll get a staged plan from where your resume says
        you are today, with something to build at each stage and a way to practice every skill with the Career Coach.
      </p>

      <div className="card sg-form">
        <label className="cc-label" htmlFor="cp-role">Role you&apos;re aiming for</label>
        <div className="sg-row">
          <input
            id="cp-role" list="cp-roles" value={role} maxLength={120}
            onChange={(e) => setRole(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") build(); }}
            placeholder="e.g. Cloud Security Engineer"
          />
          <datalist id="cp-roles">{suggestions.map((s) => <option key={s} value={s} />)}</datalist>
        </div>
        <div className="cp-opts">
          <label>
            <span className="cc-label">Time you want to take</span>
            <select value={months} onChange={(e) => setMonths(Number(e.target.value))}>
              {[3, 6, 12, 18, 24, 36].map((m) => <option key={m} value={m}>{m} months</option>)}
            </select>
          </label>
          <label>
            <span className="cc-label">Hours a week</span>
            <select value={hours} onChange={(e) => setHours(Number(e.target.value))}>
              {[2, 5, 8, 12, 20].map((h) => <option key={h} value={h}>{h} hours</option>)}
            </select>
          </label>
          <button className="btn btn-primary" onClick={() => build()} disabled={busy || role.trim().length < 2}>
            {busy ? "Building your plan…" : "Build my plan"}
          </button>
        </div>
        {error && <p className="cc-error" role="alert">{error}</p>}
      </div>

      {plan && (
        <>
          <div className="card sg-summary">
            <h2>{plan.target_role}</h2>
            <p><strong>Where you are.</strong> {plan.where_you_are}</p>
            {plan.target_summary && <p><strong>The role.</strong> {plan.target_summary}</p>}
            <p className="cp-fit"><span className={`sg-badge cp-fit-${plan.fit}`}>{FIT_LABEL[plan.fit] || plan.fit}</span></p>
            {plan.realistic_timeline && <p className="sg-next"><strong>Realistic timeline:</strong> {plan.realistic_timeline}</p>}
            {plan.honest_note && <p className="muted sg-basis">{plan.honest_note}</p>}
            <p className="muted" style={{ margin: "10px 0 0", fontSize: 13 }}>Need a certification or board exam for this role? <Link href={`/dashboard/exam-prep?exam=${encodeURIComponent(plan.target_role)}`}>Start exam prep</Link></p>
            {plan.stages[0] && (
              <p style={{ margin: "14px 0 0" }}>
                <button className="btn btn-primary" onClick={() => teachAsCourse(plan.stages[0])} disabled={!!courseBusy}>
                  {courseBusy === plan.stages[0].name ? "Building your syllabus…" : `Start the course: ${plan.stages[0].name}`}
                </button>
              </p>
            )}
          </div>

          {plan.bridge_roles.length > 0 && (
            <>
              <h2>Steps along the way</h2>
              <ul className="sg-strengths">
                {plan.bridge_roles.map((b) => (
                  <li key={b.title}><strong>{b.title}</strong>{b.why && <span className="muted"> — {b.why}</span>}</li>
                ))}
              </ul>
            </>
          )}

          <h2>The plan</h2>
          {plan.stages.map((s, i) => (
            <div className="card cp-stage" key={s.name + i}>
              <div className="sg-gap-head">
                <h3>{s.name}</h3>
                {s.when && <span className="sg-badge">{s.when}</span>}
              </div>
              {s.goal && <p>{s.goal}</p>}
              {s.skills.length > 0 && <p className="muted" style={{ margin: "8px 0 2px", fontSize: "0.85rem" }}>Skills in this stage (click one to practice just that):</p>}
              {s.skills.length > 0 && (
                <div className="cp-skills">
                  {s.skills.map((k) => (
                    <Link key={k} className="pill cp-skill" href={practiceLink(plan.target_role, k)} title="Practice this with the coach">{k}</Link>
                  ))}
                </div>
              )}
              {s.proof && <p className="sg-ex"><strong>Build this:</strong> {s.proof}</p>}
              {s.milestone && <p className="muted" style={{ margin: 0 }}>Done when: {s.milestone}</p>}
              <p style={{ margin: "12px 0 0", display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button className={i === 0 ? "btn btn-primary btn-sm" : "btn btn-ghost btn-sm"} onClick={() => teachAsCourse(s)} disabled={!!courseBusy}>
                  {courseBusy === s.name ? "Building your syllabus…" : "Teach me this as a course"}
                </button>
                <Link className="btn btn-ghost btn-sm" href={stageLink(plan.target_role, s)}>
                  Quick practice session
                </Link>
              </p>
            </div>
          ))}

          {plan.first_week.length > 0 && (
            <>
              <h2>This week</h2>
              <ul className="sg-strengths">{plan.first_week.map((x) => <li key={x}>{x}</li>)}</ul>
            </>
          )}

          <p className="muted sg-basis">
            An AI plan built from your resume, with no live job-market data: treat the timeline as an estimate.{" "}
            {plan.cached ? `Saved ${formatWhen(plan.created_at)}. ` : ""}
            <button className="sg-link" onClick={() => build(true)} disabled={busy}>Build a new version</button>
          </p>
        </>
      )}
    </div>
  );
}
