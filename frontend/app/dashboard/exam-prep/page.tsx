"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, CoachCourse, ExamQuestionOut, ExamResult, ExamRun, ExamView } from "@/lib/api";
import { clockText } from "@/lib/sessionClock";

// Study for a certification or board exam: the outline by domain, practice
// questions with the reason behind each answer, a timed mock exam scored by
// domain, and spaced review of what you missed. Questions are AI-written study
// aids, not real exam items, and the page says so.

type Feedback = { correct: boolean; correct_index: number; explanation: string };

function Runner({ run, onDone }: { run: ExamRun; onDone: (r: ExamResult) => void }) {
  const mock = run.kind === "mock";
  const [i, setI] = useState(0);
  const [picked, setPicked] = useState<Record<number, number>>({});
  const [fb, setFb] = useState<Record<number, Feedback>>({});
  const [left, setLeft] = useState(run.time_limit_min * 60);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const finished = useRef(false);
  const q: ExamQuestionOut = run.questions[i];

  async function finish() {
    if (finished.current) return;
    finished.current = true;
    setBusy(true);
    try {
      const answers = Object.entries(picked).map(([k, v]) => ({ question_id: Number(k), choice: v }));
      onDone(await api<ExamResult>(`/exams/attempts/${run.attempt_id}/finish`, { method: "POST", body: JSON.stringify({ answers: mock ? answers : [] }) }));
    } catch (e: any) {
      finished.current = false;
      setBusy(false);
      setErr(e.message || "Couldn't finish. Try again.");
    }
  }

  useEffect(() => {
    if (!mock || !run.time_limit_min) return;
    const t = setInterval(() => setLeft((s) => s - 1), 1000);
    return () => clearInterval(t);
  }, [mock, run.time_limit_min]);
  useEffect(() => {
    if (mock && run.time_limit_min && left <= 0) finish();
  }, [left]); // eslint-disable-line react-hooks/exhaustive-deps

  async function choose(n: number) {
    if (picked[q.id] !== undefined && (!mock || busy)) return;
    setPicked({ ...picked, [q.id]: n });
    if (!mock) {
      try {
        const f = await api<Feedback>(`/exams/attempts/${run.attempt_id}/answer`, { method: "POST", body: JSON.stringify({ question_id: q.id, choice: n }) });
        setFb((o) => ({ ...o, [q.id]: f }));
      } catch (e: any) {
        setErr(e.message || "Couldn't check that answer.");
      }
    }
  }

  const f = fb[q.id];
  const last = i === run.questions.length - 1;
  const answeredAll = Object.keys(picked).length === run.questions.length;
  return (
    <div className="ex-run">
      <div className="ex-bar">
        <span>Question {i + 1} of {run.questions.length}</span>
        {mock && run.time_limit_min > 0 && <span className={left < 60 ? "ex-time ex-low" : "ex-time"}>{clockText(left)} left</span>}
      </div>
      <p className="ex-stem">{q.stem}</p>
      <div className="ex-opts">
        {q.options.map((o, n) => {
          const cls = ["ex-opt"];
          if (picked[q.id] === n) cls.push("is-picked");
          if (f && n === f.correct_index) cls.push("is-right");
          if (f && picked[q.id] === n && !f.correct) cls.push("is-wrong");
          return (
            <button key={n} className={cls.join(" ")} onClick={() => choose(n)} disabled={!mock && picked[q.id] !== undefined}>
              <span className="ex-letter">{"ABCD"[n]}</span>{o}
            </button>
          );
        })}
      </div>
      {f && (
        <div className="ex-why">
          <strong>{f.correct ? "Correct." : `Not quite. The answer is ${"ABCD"[f.correct_index]}.`}</strong> {f.explanation}
        </div>
      )}
      {err && <p className="error">{err}</p>}
      <div className="ex-nav">
        <button className="btn btn-ghost btn-sm" onClick={() => setI(i - 1)} disabled={i === 0}>Back</button>
        {!last && <button className="btn btn-primary btn-sm" onClick={() => setI(i + 1)} disabled={!mock && picked[q.id] === undefined}>Next question</button>}
        {last && (
          <button className="btn btn-primary btn-sm" onClick={finish} disabled={busy || (!mock && picked[q.id] === undefined)}>
            {busy ? "Scoring…" : mock && !answeredAll ? `Finish with ${run.questions.length - Object.keys(picked).length} blank` : "See my results"}
          </button>
        )}
      </div>
    </div>
  );
}

function Results({ r, exam, onBack, onCourse, busyCourse }: { r: ExamResult; exam: ExamView; onBack: () => void; onCourse: (name: string) => void; busyCourse: string }) {
  return (
    <div className="ex-res">
      <h2 style={{ margin: 0 }}>{r.score}% <span className="muted" style={{ fontSize: 15, fontWeight: 400 }}>{r.total} questions, {r.answered} answered</span></h2>
      <div className="ex-doms">
        {r.domains.map((d) => (
          <div key={d.id} className="ex-dom-row">
            <span>{d.name}</span>
            <span className="ex-meter"><span style={{ width: `${d.pct}%` }} className={d.pct < 70 ? "is-weak" : ""} /></span>
            <span>{d.correct}/{d.total}</span>
          </div>
        ))}
      </div>
      {r.study_next.length > 0 && (
        <div className="ex-next">
          <strong>Study these next</strong>
          {r.study_next.map((s) => (
            <div key={s.id} className="ex-next-row">
              <span>{s.name}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => onCourse(s.name)} disabled={!!busyCourse}>
                {busyCourse === s.name ? "Building…" : "Teach me this as a course"}
              </button>
            </div>
          ))}
        </div>
      )}
      <h3>Every question, with the reason</h3>
      {r.review.map((q, n) => (
        <details key={q.id} className="ex-item">
          <summary className={q.chosen === q.correct ? "ex-ok" : "ex-bad"}>{n + 1}. {q.stem}</summary>
          <p style={{ margin: "8px 0 4px" }}>Your answer: {q.chosen === undefined || q.chosen === null ? "none" : `${"ABCD"[q.chosen]}. ${q.options[q.chosen]}`}</p>
          <p style={{ margin: "0 0 4px" }}>Right answer: {"ABCD"[q.correct]}. {q.options[q.correct]}</p>
          <p className="muted" style={{ margin: 0 }}>{q.explanation}</p>
        </details>
      ))}
      <p className="muted" style={{ fontSize: 13 }}>{r.note}</p>
      <button className="btn btn-primary btn-sm" onClick={onBack}>Back to {exam.name}</button>
    </div>
  );
}

function ExamPrepInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [list, setList] = useState<{ id: number; exam_name: string }[] | null>(null);
  const [exam, setExam] = useState<ExamView | null>(null);
  const [name, setName] = useState(params.get("exam") || "");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [run, setRun] = useState<ExamRun | null>(null);
  const [result, setResult] = useState<ExamResult | null>(null);
  const [mockSize, setMockSize] = useState(20);

  useEffect(() => {
    api<{ id: number; exam_name: string }[]>("/exams").then(setList).catch(() => setList([]));
  }, []);

  async function open(id: number) {
    setError("");
    try { setExam(await api<ExamView>(`/exams/${id}`)); } catch (e: any) { setError(e.message); }
  }
  async function create() {
    if (!name.trim() || busy) return;
    setBusy("create"); setError("");
    try { setExam(await api<ExamView>("/exams", { method: "POST", body: JSON.stringify({ exam_name: name.trim() }) })); }
    catch (e: any) { setError(e.message || "Couldn't build the outline."); }
    setBusy("");
  }
  async function start(kind: string, path: string, body: object) {
    if (!exam || busy) return;
    setBusy(kind); setError("");
    try { setRun(await api<ExamRun>(`/exams/${exam.id}/${path}`, { method: "POST", body: JSON.stringify(body) })); }
    catch (e: any) { setError(e.message || "Couldn't start."); }
    setBusy("");
  }
  async function done(r: ExamResult) {
    setRun(null); setResult(r);
    if (exam) setExam(await api<ExamView>(`/exams/${exam.id}`));
  }
  async function course(domain: string) {
    if (!exam || busy) return;
    setBusy(domain); setError("");
    try {
      const c = await api<CoachCourse>("/career-coach/courses", { method: "POST", body: JSON.stringify({ target_role: exam.name, topic: domain.slice(0, 200), skills: [] }) });
      router.push(`/dashboard/career-coach?course=${c.id}`);
    } catch (e: any) { setError(e.message || "Couldn't build the course."); setBusy(""); }
  }
  async function remove() {
    if (!exam || !confirm("Delete this exam and its questions?")) return;
    await api(`/exams/${exam.id}`, { method: "DELETE" });
    setExam(null); setResult(null);
    setList((l) => (l || []).filter((x) => x.id !== exam.id));
  }

  if (run) return <div><h1>{exam?.name}</h1><Runner run={run} onDone={done} /></div>;
  if (exam && result) return <div><h1>{exam.name}</h1><Results r={result} exam={exam} onBack={() => setResult(null)} onCourse={course} busyCourse={busy} /></div>;

  if (exam) {
    return (
      <div>
        <p><button className="btn btn-ghost btn-sm" onClick={() => setExam(null)}>All exams</button></p>
        <h1 style={{ marginBottom: 4 }}>{exam.name}</h1>
        <p className="muted" style={{ marginTop: 0 }}>{exam.summary}{exam.body ? ` Set by ${exam.body}.` : ""}</p>
        <div className="ex-note">
          {exam.confidence === "low" ? "I don't know this exam well, so this is a general outline of the subject. " : ""}
          {exam.note}
        </div>
        <div className="ex-doms">
          {exam.domains.map((d) => (
            <div key={d.id} className="ex-domain">
              <div className="ex-domain-head">
                <strong>{d.name}</strong>
                <span className="muted">about {d.weight_pct}% of the exam</span>
              </div>
              <p className="muted" style={{ margin: "4px 0 8px", fontSize: 13 }}>{d.topics.join(" · ")}</p>
              <div className="ex-domain-foot">
                <span className="muted" style={{ fontSize: 13 }}>
                  {d.answered ? `${d.accuracy}% correct over ${d.answered} answers` : "Not started"}{d.due ? ` · ${d.due} due for review` : ""}
                </span>
                <button className="btn btn-ghost btn-sm" onClick={() => start(d.id, "practice", { domain_id: d.id, count: 5 })} disabled={!!busy}>
                  {busy === d.id ? "Writing questions…" : "Practice 5"}
                </button>
              </div>
            </div>
          ))}
        </div>
        <div className="ex-actions">
          <select value={mockSize} onChange={(e) => setMockSize(Number(e.target.value))} aria-label="Mock exam length">
            <option value={20}>20 questions</option>
            <option value={40}>40 questions</option>
          </select>
          <button className="btn btn-primary" onClick={() => start("mock", "mock", { count: mockSize })} disabled={!!busy}>
            {busy === "mock" ? "Building your mock exam…" : "Start a timed mock exam"}
          </button>
          <button className="btn btn-ghost" onClick={() => start("review", "review", { count: 10 })} disabled={!!busy || exam.due === 0}>
            {exam.due ? `Review ${Math.min(exam.due, 10)} missed` : "Nothing due for review"}
          </button>
          <button className="btn btn-ghost" onClick={remove}>Delete exam</button>
        </div>
        {error && <p className="error">{error}</p>}
      </div>
    );
  }

  return (
    <div>
      <h1>Exam prep</h1>
      <p className="muted">Studying for a certification or board exam? Name it and get the content areas, practice questions with the reason behind each answer, a timed mock exam, and review of what you missed.</p>
      <div className="ex-create">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Which exam? For example CISA, CPA, NCLEX-RN, PMP" maxLength={120} onKeyDown={(e) => e.key === "Enter" && create()} />
        <button className="btn btn-primary" onClick={create} disabled={busy === "create" || name.trim().length < 2}>
          {busy === "create" ? "Building the outline…" : "Build my study plan"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {list && list.length > 0 && (
        <>
          <h3>Your exams</h3>
          {list.map((x) => (
            <p key={x.id} style={{ margin: "6px 0" }}><button className="btn btn-ghost btn-sm" onClick={() => open(x.id)}>{x.exam_name}</button></p>
          ))}
        </>
      )}
    </div>
  );
}

export default function ExamPrepPage() {
  return <Suspense fallback={null}><ExamPrepInner /></Suspense>;
}
