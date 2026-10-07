"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, CareerCoachSession, CareerCoachSessionType, CoachingMessage } from "@/lib/api";

// The individual-product AI Career Coach: practice for any role or field
// the person types in (no employer or application needed), plus resume
// coaching aimed at that same role. Separate from CoachingPanel, which is
// the Enterprise Job Buddy's practice for an employee's actual role.
// Self-contained: own state, own api() calls. Quota (429) is handled
// globally by api() via the quota modal, so errors here are shown inline.

const SESSION_TYPES: { value: CareerCoachSessionType; label: string; hint: string }[] = [
  { value: "drill", label: "Knowledge drill", hint: "Quick-fire questions that test real understanding of the field" },
  { value: "walkthrough", label: "Task walkthrough", hint: "Work through a realistic task from the job, step by step" },
  { value: "interview", label: "Mock interview", hint: "A hiring manager interviews you for this role" },
  { value: "resume", label: "Resume coaching", hint: "Gap analysis for this role, then bullet-by-bullet rewrites" },
];

const typeLabel = (t: CareerCoachSessionType) => SESSION_TYPES.find((x) => x.value === t)?.label ?? t;

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="hint">Not scored</span>;
  return <span className={score >= 80 ? "ticket high" : "ticket"}><span className="score">{score}</span>/100</span>;
}

export default function CareerCoachPage() {
  const [sessions, setSessions] = useState<CareerCoachSession[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [active, setActive] = useState<CareerCoachSession | null>(null);
  const [messages, setMessages] = useState<CoachingMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [error, setError] = useState("");

  const [role, setRole] = useState("");
  const [type, setType] = useState<CareerCoachSessionType>("drill");
  const [topic, setTopic] = useState("");
  const [starting, setStarting] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<CareerCoachSession[]>("/career-coach/sessions")
      .then(setSessions)
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  async function start() {
    if (starting || role.trim().length < 2) return;
    setStarting(true);
    setError("");
    try {
      const r = await api<{ session: CareerCoachSession; opening_message: CoachingMessage }>(
        "/career-coach/sessions",
        { method: "POST", body: JSON.stringify({ session_type: type, target_role: role.trim(), topic: topic.trim() }) }
      );
      setSessions((s) => [r.session, ...s]);
      setActive(r.session);
      setMessages([r.opening_message]);
      setTopic("");
    } catch (err: any) {
      setError(err.message || "Couldn't start a session — try again.");
    } finally {
      setStarting(false);
    }
  }

  async function open(s: CareerCoachSession) {
    setError("");
    setActive(s);
    setMessages([]);
    try {
      setMessages(await api<CoachingMessage[]>(`/career-coach/sessions/${s.id}/messages`));
    } catch (err: any) {
      setError(err.message || "Couldn't load that session.");
      setActive(null);
    }
  }

  async function send() {
    if (!input.trim() || sending || !active) return;
    const text = input;
    setInput("");
    setSending(true);
    setError("");
    setMessages((m) => [...m, { id: -Date.now(), role: "user", content: text, created_at: new Date().toISOString() }]);
    try {
      const reply = await api<CoachingMessage>(`/career-coach/sessions/${active.id}/messages`, {
        method: "POST", body: JSON.stringify({ message: text }),
      });
      setMessages((m) => [...m, reply]);
    } catch (err: any) {
      setError(err.message || "Coach couldn't respond — your message was saved, try again.");
    } finally {
      setSending(false);
    }
  }

  async function end() {
    if (!active || completing) return;
    if (!messages.some((m) => m.role === "user")) {
      setError("Send at least one reply before ending the session.");
      return;
    }
    setCompleting(true);
    setError("");
    try {
      const updated = await api<CareerCoachSession>(`/career-coach/sessions/${active.id}/complete`, { method: "POST" });
      setActive(updated);
      setSessions((s) => s.map((row) => (row.id === updated.id ? updated : row)));
    } catch (err: any) {
      setError(err.message || "Couldn't score this session — try again.");
    } finally {
      setCompleting(false);
    }
  }

  return (
    <div>
      <h1>Career Coach</h1>
      <p className="hint">
        Pick any role or field you&apos;re aiming for and practice it: drills, real tasks, mock interviews,
        and resume coaching — with honest scores and feedback. Your resume is used for context
        (<Link href="/dashboard/resume">edit it here</Link>), and the coach never invents experience for you.
      </p>

      {error && <div className="card" style={{ borderColor: "var(--danger, #c0392b)" }}>{error}</div>}

      {!active && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Start a session</h3>
          <input
            placeholder="Role or field you're aiming for (e.g. Data Analyst, UX Designer, ICU Nurse)"
            value={role} maxLength={120} onChange={(e) => setRole(e.target.value)}
            style={{ width: "100%", marginBottom: 12 }}
          />
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
            {SESSION_TYPES.map((t) => (
              <label key={t.value} style={{ display: "flex", alignItems: "flex-start", gap: 8, cursor: "pointer" }}>
                <input type="radio" name="cc-type" checked={type === t.value}
                       onChange={() => setType(t.value)} style={{ marginTop: 3 }} />
                <span>
                  <div style={{ fontWeight: 600 }}>{t.label}</div>
                  <div className="hint">{t.hint}</div>
                </span>
              </label>
            ))}
          </div>
          <input
            placeholder={type === "resume" ? "Section to focus on (optional)" : "Topic (optional — leave blank and the coach picks one)"}
            value={topic} maxLength={200} onChange={(e) => setTopic(e.target.value)}
            style={{ width: "100%", marginBottom: 12 }}
          />
          <button className="btn btn-primary" onClick={start} disabled={starting || role.trim().length < 2}>
            {starting ? "Starting…" : "Start"}
          </button>
        </div>
      )}

      {active && (
        <div className="card">
          <div className="card-row" style={{ marginBottom: 4 }}>
            <div>
              <strong>{active.topic}</strong>{" "}
              <span className="hint">{typeLabel(active.session_type)} · {active.target_role}</span>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setActive(null)}>Close</button>
          </div>

          <div className="chat-window" style={{ maxHeight: 420, padding: "12px 0" }}>
            {messages.map((m) => (
              <div key={m.id} className={`chat-bubble ${m.role}`} style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
            ))}
            {sending && <div className="chat-bubble assistant muted">Thinking…</div>}
            <div ref={endRef} />
          </div>

          {active.status === "completed" ? (
            <div className="card" style={{ background: "var(--paper)", marginTop: 8 }}>
              <div className="card-row">
                <h4 style={{ margin: 0 }}>Session complete</h4>
                <ScoreBadge score={active.score} />
              </div>
              <p style={{ marginTop: 8, marginBottom: 0 }}>{active.feedback}</p>
            </div>
          ) : (
            <>
              <div className="chat-input-row">
                <textarea
                  value={input} onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
                  }}
                  placeholder={active.session_type === "resume" ? "Paste a bullet or section to rewrite…" : "Your reply…"}
                />
                <button className="btn btn-primary" onClick={send} disabled={sending || !input.trim()}>Send</button>
              </div>
              <button className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={end} disabled={completing}>
                {completing ? "Scoring…" : "End session & get feedback"}
              </button>
            </>
          )}
        </div>
      )}

      {loaded && sessions.length > 0 && (
        <div className="card">
          <p className="hint" style={{ marginTop: 0, marginBottom: 8 }}>Past sessions</p>
          {sessions.map((s) => (
            <div key={s.id} className="points-event-row" style={{ cursor: "pointer" }} onClick={() => open(s)}>
              <div>
                <div style={{ fontWeight: 600 }}>{s.topic}</div>
                <div className="hint">
                  {typeLabel(s.session_type)} · {s.target_role} · {s.status === "completed" ? "Completed" : "In progress"}
                </div>
              </div>
              <ScoreBadge score={s.score} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
