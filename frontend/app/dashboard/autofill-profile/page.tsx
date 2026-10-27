"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, AfEdu, AfWork, AutofillProfile } from "@/lib/api";
import UnansweredQuestions from "@/components/UnansweredQuestions";

// The details application forms ask for again and again, kept once. The
// Riseply browser extension fills them in. Nothing here is guessed: work
// authorization, salary and demographic answers stay blank until you choose
// them, and the extension leaves a question alone when its answer is blank.

const YES_NO = [["", "Leave blank"], ["yes", "Yes"], ["no", "No"]];
const EEO: { key: string; label: string; options: string[] }[] = [
  { key: "gender", label: "Gender", options: ["Man", "Woman", "Non-binary", "Decline to answer"] },
  { key: "race", label: "Race or ethnicity", options: ["Asian", "Black or African American", "Hispanic or Latino", "White", "Two or more races", "Native American or Alaska Native", "Native Hawaiian or Pacific Islander", "Other", "Decline to answer"] },
  { key: "veteran", label: "Veteran status", options: ["Yes", "No", "Decline to answer"] },
  { key: "disability", label: "Disability status", options: ["Yes", "No", "Decline to answer"] },
  { key: "hispanic", label: "Hispanic or Latino?", options: ["Yes", "No", "Decline to answer"] },
];
const YES_NO_QUESTIONS: [string, string][] = [
  ["over_18", "Are you 18 or older?"],
  ["previously_employed", "Have you worked for the company before? (usual answer)"],
  ["has_employee_relationship", "Personal relationship with a current employee? (usual answer)"],
  ["restrictive_agreement", "Bound by an agreement that limits where you can work? (usual answer)"],
  ["government_official", "Current or recent government official?"],
  ["related_to_official", "Related to a government official?"],
];
const blankWork: AfWork = { company: "", title: "", location: "", start: "", end: "", current: false, summary: "" };
const blankEdu: AfEdu = { school: "", degree: "", field: "", start: "", end: "" };

export default function AutofillProfilePage() {
  const [p, setP] = useState<AutofillProfile | null>(null);
  const [hasResume, setHasResume] = useState(true);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ profile: AutofillProfile; has_resume: boolean }>("/autofill-profile")
      .then((r) => { setP(r.profile); setHasResume(r.has_resume); })
      .catch((e) => setError(e.message || "Couldn't load your profile."));
  }, []);

  function change(next: AutofillProfile) { setP(next); setDirty(true); setMsg(""); }

  async function save() {
    if (!p) return;
    setBusy("save"); setError("");
    try {
      const r = await api<{ profile: AutofillProfile }>("/autofill-profile", { method: "PUT", body: JSON.stringify({ profile: p }) });
      setP(r.profile); setDirty(false); setMsg("Saved. The extension will use this the next time it fills a form.");
    } catch (e: any) { setError(e.message || "Couldn't save."); }
    setBusy("");
  }

  async function fromResume() {
    if (dirty && !confirm("This replaces your work history, education and skills below with what's in your resume. Your answers stay. Continue?")) return;
    if (!dirty && p && (p.work.length || p.education.length) && !confirm("This replaces your work history, education and skills with what's in your resume. Continue?")) return;
    setBusy("resume"); setError("");
    try {
      const r = await api<{ profile: AutofillProfile }>("/autofill-profile/from-resume", { method: "POST" });
      setP(r.profile); setDirty(false); setMsg("Filled from your resume. Check each entry, fix anything, and it saves as it is.");
    } catch (e: any) { setError(e.message || "Couldn't read your resume."); }
    setBusy("");
  }

  if (!p) return <div><h1>Autofill profile</h1>{error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}</div>;

  const setWork = (i: number, patch: Partial<AfWork>) => change({ ...p, work: p.work.map((w, n) => (n === i ? { ...w, ...patch } : w)) });
  const setEdu = (i: number, patch: Partial<AfEdu>) => change({ ...p, education: p.education.map((e, n) => (n === i ? { ...e, ...patch } : e)) });
  const setAns = (k: string, v: string) => change({ ...p, answers: { ...p.answers, [k]: v } });
  const setContact = (k: string, v: string) => change({ ...p, contact: { ...(p.contact || {}), [k]: v } });

  return (
    <div className="af">
      <h1>Autofill profile</h1>
      <p className="muted">The details application forms ask for again and again. The Riseply browser extension fills them in for you. You review every form and press Submit yourself.</p>

      <div className="card af-top">
        <div>
          <strong>Start from your resume</strong>
          <p className="muted" style={{ margin: "2px 0 0", fontSize: 13 }}>
            {hasResume ? "Riseply reads your default resume and fills in work history, education and skills. It only copies what the resume says." : "Add your resume first, then Riseply can read it."}
            {!hasResume && <> <Link href="/dashboard/resume">Go to Resume</Link></>}
          </p>
        </div>
        <button className="btn btn-primary btn-sm" onClick={fromResume} disabled={!hasResume || !!busy}>{busy === "resume" ? "Reading your resume…" : "Fill from my resume"}</button>
      </div>

      <UnansweredQuestions onSaved={(prof) => { setP(prof); setDirty(false); }} />

      <h2>Work history</h2>
      {p.work.map((w, i) => (
        <div key={i} className="card af-item">
          <div className="af-grid">
            <label>Job title<input value={w.title} onChange={(e) => setWork(i, { title: e.target.value })} /></label>
            <label>Company<input value={w.company} onChange={(e) => setWork(i, { company: e.target.value })} /></label>
            <label>Location<input value={w.location} onChange={(e) => setWork(i, { location: e.target.value })} /></label>
            <label>Start<input value={w.start} placeholder="Jan 2020" onChange={(e) => setWork(i, { start: e.target.value })} /></label>
            <label>End<input value={w.current ? "Present" : w.end} disabled={w.current} placeholder="Mar 2023" onChange={(e) => setWork(i, { end: e.target.value })} /></label>
            <label className="af-check"><input type="checkbox" checked={w.current} onChange={(e) => setWork(i, { current: e.target.checked })} /> I work here now</label>
          </div>
          <label>What you did<textarea rows={3} value={w.summary} onChange={(e) => setWork(i, { summary: e.target.value })} /></label>
          <button className="btn btn-ghost btn-sm" onClick={() => change({ ...p, work: p.work.filter((_, n) => n !== i) })}>Remove this job</button>
        </div>
      ))}
      {p.work.length < 10 && <button className="btn btn-ghost btn-sm" onClick={() => change({ ...p, work: [...p.work, { ...blankWork }] })}>Add a job</button>}

      <h2>Education</h2>
      {p.education.map((e, i) => (
        <div key={i} className="card af-item">
          <div className="af-grid">
            <label>School<input value={e.school} onChange={(ev) => setEdu(i, { school: ev.target.value })} /></label>
            <label>Degree<input value={e.degree} placeholder="B.S., M.S., …" onChange={(ev) => setEdu(i, { degree: ev.target.value })} /></label>
            <label>Field of study<input value={e.field} onChange={(ev) => setEdu(i, { field: ev.target.value })} /></label>
            <label>Start<input value={e.start} onChange={(ev) => setEdu(i, { start: ev.target.value })} /></label>
            <label>End<input value={e.end} onChange={(ev) => setEdu(i, { end: ev.target.value })} /></label>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={() => change({ ...p, education: p.education.filter((_, n) => n !== i) })}>Remove this school</button>
        </div>
      ))}
      {p.education.length < 5 && <button className="btn btn-ghost btn-sm" onClick={() => change({ ...p, education: [...p.education, { ...blankEdu }] })}>Add a school</button>}

      <h2>Skills</h2>
      <label>One per line, or separated by commas
        <textarea rows={3} defaultValue={p.skills.join(", ")} key={p.skills.join("|")}
          onBlur={(e) => change({ ...p, skills: e.target.value.split(/[\n,]/).map((s) => s.trim()).filter(Boolean).slice(0, 30) })} />
      </label>

      <h2>Address and phone</h2>
      <p className="muted" style={{ marginTop: 0 }}>Used for the address and phone sections of application forms. Blank fields are skipped.</p>
      <div className="card af-grid">
        <label>Address line 1<input value={p.contact?.address_line1 || ""} onChange={(e) => setContact("address_line1", e.target.value)} /></label>
        <label>Address line 2<input value={p.contact?.address_line2 || ""} onChange={(e) => setContact("address_line2", e.target.value)} /></label>
        <label>City<input value={p.contact?.city || ""} onChange={(e) => setContact("city", e.target.value)} /></label>
        <label>State<input value={p.contact?.state || ""} placeholder="e.g. IL or Illinois" onChange={(e) => setContact("state", e.target.value)} /></label>
        <label>Postal code<input value={p.contact?.postal_code || ""} onChange={(e) => setContact("postal_code", e.target.value)} /></label>
        <label>Country<input value={p.contact?.country || ""} placeholder="e.g. United States" onChange={(e) => setContact("country", e.target.value)} /></label>
        <label>Phone type
          <select value={p.contact?.phone_type || ""} onChange={(e) => setContact("phone_type", e.target.value)}>
            <option value="">Mobile (default)</option>
            {["Mobile", "Home", "Work"].map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </label>
      </div>

      <h2>Standard answers</h2>
      <p className="muted" style={{ marginTop: 0 }}>The extension answers these questions only when you choose an answer here. Leave one blank and it skips that question.</p>
      <div className="card af-grid">
        {[["work_authorized_us", "Legally authorized to work in the US?"], ["needs_sponsorship", "Will you need visa sponsorship?"], ["willing_to_relocate", "Willing to relocate?"]].map(([k, label]) => (
          <label key={k}>{label}
            <select value={p.answers[k] || ""} onChange={(e) => setAns(k, e.target.value)}>{YES_NO.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          </label>
        ))}
        <label>Salary expectation<input value={p.answers.salary_expectation || ""} placeholder="e.g. $120,000" onChange={(e) => setAns("salary_expectation", e.target.value)} /></label>
        <label>Notice period<input value={p.answers.notice_period || ""} placeholder="e.g. Two weeks" onChange={(e) => setAns("notice_period", e.target.value)} /></label>
        <label>Earliest start date<input value={p.answers.earliest_start_date || ""} placeholder="e.g. Immediately" onChange={(e) => setAns("earliest_start_date", e.target.value)} /></label>
        <label>How did you hear about us?<input value={p.answers.referral_source || ""} placeholder="e.g. Indeed" onChange={(e) => setAns("referral_source", e.target.value)} /></label>
      </div>
      <p className="muted">Questions many employers repeat. These fill only when you choose an answer, and you can change any of them on the form.</p>
      <div className="card af-grid">
        {YES_NO_QUESTIONS.map(([k, label]) => (
          <label key={k}>{label}
            <select value={p.answers[k] || ""} onChange={(e) => setAns(k, e.target.value)}>{YES_NO.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          </label>
        ))}
      </div>

      <h2>Voluntary self-identification</h2>
      <p className="muted" style={{ marginTop: 0 }}>Many US applications ask these. They're optional and you choose what to answer. Blank means the extension leaves the question for you. "Decline to answer" fills that choice. Riseply never fills these on its own.</p>
      <div className="card af-grid">
        {EEO.map((f) => (
          <label key={f.key}>{f.label}
            <select value={p.eeo[f.key] || ""} onChange={(e) => change({ ...p, eeo: { ...p.eeo, [f.key]: e.target.value } })}>
              <option value="">Leave blank</option>
              {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
        ))}
      </div>

      <h2>Saved answers</h2>
      <p className="muted" style={{ marginTop: 0 }}>Questions you get asked a lot, answered once in your own words. The extension uses these before it drafts anything new.</p>
      {p.saved_answers.map((qa, i) => (
        <div key={i} className="card af-item">
          <label>Question<input value={qa.question} placeholder="Why do you want to work here?" onChange={(e) => change({ ...p, saved_answers: p.saved_answers.map((x, n) => (n === i ? { ...x, question: e.target.value } : x)) })} /></label>
          <label>Your answer<textarea rows={3} value={qa.answer} onChange={(e) => change({ ...p, saved_answers: p.saved_answers.map((x, n) => (n === i ? { ...x, answer: e.target.value } : x)) })} /></label>
          <button className="btn btn-ghost btn-sm" onClick={() => change({ ...p, saved_answers: p.saved_answers.filter((_, n) => n !== i) })}>Remove</button>
        </div>
      ))}
      {p.saved_answers.length < 30 && <button className="btn btn-ghost btn-sm" onClick={() => change({ ...p, saved_answers: [...p.saved_answers, { question: "", answer: "" }] })}>Add a question</button>}

      <div className="af-save">
        <button className="btn btn-primary" onClick={save} disabled={!dirty || !!busy}>{busy === "save" ? "Saving…" : "Save changes"}</button>
        {dirty && <span className="muted">You have unsaved changes.</span>}
        {msg && !dirty && <span className="muted">{msg}</span>}
        {error && <span className="error">{error}</span>}
      </div>
    </div>
  );
}
