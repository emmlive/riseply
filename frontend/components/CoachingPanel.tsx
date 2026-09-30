"use client";

import { useEffect, useState } from "react";
import { api, CoachingMessage, CoachingSession, CoachingSessionType } from "@/lib/api";

// Practical, role-specific training -- distinct from the onboarding
// plan (a static document, shown elsewhere on this page) and the Job
// Buddy chat (an open-ended mentor conversation with no defined end).
// A coaching session is a short, bounded exercise: pick a type and
// optional topic, work through it with the coach, then end it for a
// score and specific feedback. Self-contained component (own state,
// own api() calls) so it can be dropped into the Job Buddy page as one
// more section without threading its state through that page's already
// very large JobBuddyChat component. Reuses the existing
// .chat-window/.chat-bubble/.chat-input-row classes the Job Buddy chat
// below already defines, rather than inventing a second chat look.

const SESSION_TYPES: { value: CoachingSessionType; label: string; hint: string }[] = [
  { value: "drill", label: "Knowledge drill", hint: "Quick judgment/knowledge questions for this role" },
  { value: "walkthrough", label: "Task walkthrough", hint: "Practice a real task for this role, step by step" },
  { value: "roleplay", label: "Roleplay scenario", hint: "Practice a real conversation (a difficult customer, a tense 1:1, etc.)" },
];

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="hint">Not scored</span>;
  const cls = score >= 80 ? "ticket high" : "ticket";
  return <span className={cls}><span className="score">{score}</span>/100</span>;
}

export default function CoachingPanel({ applicationId }: { applicationId: number }) {
  const [sessions, setSessions] = useState<CoachingSession[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [activeSession, setActiveSession] = useState<CoachingSession | null>(null);
  const [messages, setMessages] = useState<CoachingMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [completing, setCompleting] = useState(false);

  const [showStartForm, setShowStartForm] = useState(false);
  const [newType, setNewType] = useState<CoachingSessionType>("drill");
  const [newTopic, setNewTopic] = useState("");
  const [starting, setStarting] = useState(false);

  async function loadSessions() {
    try {
      const rows = await api<CoachingSession[]>(`/applications/${applicationId}/coaching/sessions`);
      setSessions(rows);
    } catch {
      // best-effort -- this section just stays empty rather than
      // blocking the rest of the Job Buddy page over one panel
    } finally {
      setLoaded(true);
    }
  }

  useEffect(() => {
    loadSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applicationId]);

  async function openSession(session: CoachingSession) {
    setActiveSession(session);
    setMessages([]);
    try {
      const rows = await api<CoachingMessage[]>(`/applications/${applicationId}/coaching/sessions/${session.id}/messages`);
      setMessages(rows);
    } catch (err: any) {
      alert(err.message || "Couldn't load that session.");
      setActiveSession(null);
    }
  }

  async function startSession() {
    if (starting) return;
    setStarting(true);
    try {
      const result = await api<{ session: CoachingSession; opening_message: CoachingMessage }>(
        `/applications/${applicationId}/coaching/sessions`,
        { method: "POST", body: JSON.stringify({ session_type: newType, topic: newTopic.trim() }) }
      );
      setSessions((s) => [result.session, ...s]);
      setActiveSession(result.session);
      setMessages([result.opening_message]);
      setShowStartForm(false);
      setNewTopic("");
    } catch (err: any) {
      alert(err.message || "Couldn't start a coaching session — try again.");
    } finally {
      setStarting(false);
    }
  }

  async function send() {
    if (!input.trim() || sending || !activeSession) return;
    const text = input;
    setInput("");
    setSending(true);
    setMessages((m) => [...m, { id: -1, role: "user", content: text, created_at: new Date().toISOString() }]);
    try {
      const reply = await api<CoachingMessage>(
        `/applications/${applicationId}/coaching/sessions/${activeSession.id}/messages`,
        { method: "POST", body: JSON.stringify({ message: text }) }
      );
      setMessages((m) => [...m, reply]);
    } catch (err: any) {
      alert(err.message || "Coach couldn't respond — try again.");
    } finally {
      setSending(false);
    }
  }

  async function endSession() {
    if (!activeSession || completing) return;
    if (messages.filter((m) => m.role === "user").length === 0) {
      alert("Send at least one reply before ending the session.");
      return;
    }
    setCompleting(true);
    try {
      const updated = await api<CoachingSession>(
        `/applications/${applicationId}/coaching/sessions/${activeSession.id}/complete`,
        { method: "POST" }
      );
      setActiveSession(updated);
      setSessions((s) => s.map((row) => (row.id === updated.id ? updated : row)));
    } catch (err: any) {
      alert(err.message || "Couldn't score this session — try again.");
    } finally {
      setCompleting(false);
    }
  }

  if (!loaded) return null;

  return (
    <div className="card">
      <div className="card-row">
        <h3 style={{ margin: 0 }}>Practice & coaching</h3>
        {!showStartForm && !activeSession && (
          <button className="btn btn-primary btn-sm" onClick={() => setShowStartForm(true)}>
            Start a session
          </button>
        )}
      </div>
      <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
        Hands-on practice for this specific role — drills, task walkthroughs, and roleplay
        scenarios, with a real score and feedback at the end. Not a quiz to pass; a place to
        actually get better.
      </p>

      {showStartForm && !activeSession && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 10 }}>
            {SESSION_TYPES.map((t) => (
              <label key={t.value} style={{ display: "flex", alignItems: "flex-start", gap: 8, cursor: "pointer" }}>
                <input type="radio" name="coaching-type" checked={newType === t.value}
                       onChange={() => setNewType(t.value)} style={{ marginTop: 3 }} />
                <span>
                  <div style={{ fontWeight: 600 }}>{t.label}</div>
                  <div className="hint">{t.hint}</div>
                </span>
              </label>
            ))}
          </div>
          <input
            placeholder="Topic (optional — leave blank and the coach will pick one for your role)"
            value={newTopic} onChange={(e) => setNewTopic(e.target.value)} style={{ width: "100%", marginBottom: 10 }}
          />
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary btn-sm" onClick={startSession} disabled={starting}>
              {starting ? "Starting…" : "Start"}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => setShowStartForm(false)}>Cancel</button>
          </div>
        </div>
      )}

      {activeSession && (
        <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12, marginBottom: 16 }}>
          <div className="card-row" style={{ marginBottom: 4 }}>
            <div>
              <strong>{activeSession.topic}</strong>{" "}
              <span className="hint">
                ({SESSION_TYPES.find((t) => t.value === activeSession.session_type)?.label})
              </span>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setActiveSession(null)}>Close</button>
          </div>

          <div className="chat-window" style={{ maxHeight: 320, padding: "12px 0" }}>
            {messages.map((m) => (
              <div key={m.id} className={`chat-bubble ${m.role}`}>{m.content}</div>
            ))}
            {sending && <div className="chat-bubble assistant muted">Thinking…</div>}
          </div>

          {activeSession.status === "completed" ? (
            <div className="card" style={{ background: "var(--paper)", marginTop: 8 }}>
              <div className="card-row">
                <h4 style={{ margin: 0 }}>Session complete</h4>
                <ScoreBadge score={activeSession.score} />
              </div>
              <p style={{ marginTop: 8, marginBottom: 0 }}>{activeSession.feedback}</p>
            </div>
          ) : (
            <>
              <div className="chat-input-row">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send();
                    }
                  }}
                  placeholder="Your reply…"
                />
                <button className="btn btn-primary" onClick={send} disabled={sending || !input.trim()}>
                  Send
                </button>
              </div>
              <button className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={endSession} disabled={completing}>
                {completing ? "Scoring…" : "End session & get feedback"}
              </button>
            </>
          )}
        </div>
      )}

      {sessions.length === 0 && !showStartForm ? (
        <p className="hint" style={{ marginBottom: 0 }}>No practice sessions yet.</p>
      ) : (
        sessions.length > 0 && (
          <div>
            {!activeSession && <p className="hint" style={{ marginTop: 0, marginBottom: 8 }}>Past sessions</p>}
            {sessions.map((s) => (
              <div key={s.id} className="points-event-row" style={{ cursor: "pointer" }} onClick={() => openSession(s)}>
                <div>
                  <div style={{ fontWeight: 600 }}>{s.topic}</div>
                  <div className="hint">
                    {SESSION_TYPES.find((t) => t.value === s.session_type)?.label} ·{" "}
                    {s.status === "completed" ? "Completed" : "In progress"}
                  </div>
                </div>
                <ScoreBadge score={s.score} />
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}
