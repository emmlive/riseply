"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, CareerCoachMessage, CareerCoachSession, CareerCoachSessionType, formatWhen, LearningStyle, LibraryItem } from "@/lib/api";
import ResourceCard from "@/components/ResourceCard";
import VisualDiagram from "@/components/VisualDiagram";
import {
  Dictation, dictationSupported, speak, speechSynthesisSupported, startDictation, stopSpeaking,
} from "@/lib/speech";

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

// How the person likes to learn. "auto" lets the coach adapt; the others
// pin a teaching approach for the whole session. Any single reply can
// also be re-taught another way with the "Explain it differently" buttons.
const LEARNING_STYLES: { value: LearningStyle; label: string; hint: string }[] = [
  { value: "auto", label: "Let the coach adapt", hint: "Switches approach when something isn't landing" },
  { value: "visual", label: "Visual", hint: "Diagrams and pictures first" },
  { value: "handson", label: "Hands-on", hint: "Try a small task first, explain after" },
  { value: "story", label: "Stories & analogies", hint: "Real-world comparisons and scenarios" },
  { value: "stepbystep", label: "Step by step", hint: "Worked examples, one step at a time" },
];

const REEXPLAIN: { style: "visual" | "stepbystep" | "story" | "handson"; label: string; message: string }[] = [
  { style: "visual", label: "Show me", message: "Can you show me that visually, with a diagram?" },
  { style: "stepbystep", label: "Step by step", message: "Can you walk me through that step by step with an example?" },
  { style: "story", label: "Analogy", message: "Can you explain that with an analogy or a real-world example?" },
  { style: "handson", label: "Let me try", message: "Can you give me something to try hands-on instead?" },
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
  const [messages, setMessages] = useState<CareerCoachMessage[]>([]);
  // "Extra learning" shelf: Library resources relevant to this session.
  const [shelf, setShelf] = useState<LibraryItem[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [error, setError] = useState("");

  const [role, setRole] = useState("");
  const [type, setType] = useState<CareerCoachSessionType>("drill");
  const [topic, setTopic] = useState("");
  const [learningStyle, setLearningStyle] = useState<LearningStyle>("auto");
  const [starting, setStarting] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  // Voice: dictation fills the reply box (you review it, then send);
  // read-aloud speaks the coach's replies. Both use on-device browser
  // APIs and are hidden where unsupported. Support is detected after
  // mount so server and client render the same markup.
  const [canDictate, setCanDictate] = useState(false);
  const [canSpeak, setCanSpeak] = useState(false);
  const [listening, setListening] = useState(false);
  const [readAloud, setReadAloud] = useState(false);
  const [speakingId, setSpeakingId] = useState<number | null>(null);
  const dictation = useRef<Dictation | null>(null);
  const dictationBase = useRef("");

  // Notepad: one note per session, autosaved shortly after you stop typing.
  const [notes, setNotes] = useState("");
  const [notesState, setNotesState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const notesTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const notesDirty = useRef(false);
  const notesSession = useRef<number | null>(null);

  useEffect(() => {
    api<CareerCoachSession[]>("/career-coach/sessions")
      .then(setSessions)
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  useEffect(() => {
    setCanDictate(dictationSupported());
    setCanSpeak(speechSynthesisSupported());
    try {
      setReadAloud(localStorage.getItem("cc-read-aloud") === "1");
    } catch { /* storage unavailable -- default off */ }
    return () => { dictation.current?.stop(); stopSpeaking(); };
  }, []);

  useEffect(() => {
    setShelf([]);
    if (!active) return;
    let cancelled = false;
    api<LibraryItem[]>(`/career-coach/sessions/${active.id}/library`)
      .then((rows) => { if (!cancelled) setShelf(rows); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [active?.id]);

  // Load the note whenever a different session is opened.
  useEffect(() => {
    if (notesTimer.current) clearTimeout(notesTimer.current);
    notesDirty.current = false;
    notesSession.current = active?.id ?? null;
    setNotes("");
    setNotesState("idle");
    if (!active) return;
    const id = active.id;
    api<{ content: string }>(`/career-coach/sessions/${id}/notes`)
      .then((n) => { if (notesSession.current === id && !notesDirty.current) setNotes(n.content || ""); })
      .catch(() => {});
  }, [active?.id]);

  function onNotesChange(value: string) {
    if (!active) return;
    const id = active.id;
    setNotes(value);
    notesDirty.current = true;
    setNotesState("saving");
    if (notesTimer.current) clearTimeout(notesTimer.current);
    notesTimer.current = setTimeout(async () => {
      try {
        await api(`/career-coach/sessions/${id}/notes`, { method: "PUT", body: JSON.stringify({ content: value }) });
        if (notesSession.current === id) setNotesState("saved");
      } catch {
        if (notesSession.current === id) setNotesState("error");
      }
    }, 800);
  }

  function toggleDictation() {
    if (listening) { dictation.current?.stop(); return; }
    stopSpeaking();
    setSpeakingId(null);
    dictationBase.current = input.trim() ? input.trimEnd() + " " : "";
    const d = startDictation(
      (text) => setInput(dictationBase.current + text),
      (err) => { setListening(false); dictation.current = null; if (err) setError(err); },
    );
    if (!d) { setError("Dictation isn't available in this browser — you can type instead."); return; }
    dictation.current = d;
    setListening(true);
  }

  function toggleReadAloud(on: boolean) {
    setReadAloud(on);
    try { localStorage.setItem("cc-read-aloud", on ? "1" : "0"); } catch { /* ignore */ }
    if (!on) { stopSpeaking(); setSpeakingId(null); }
  }

  function playMessage(m: CareerCoachMessage) {
    if (speakingId === m.id) { stopSpeaking(); setSpeakingId(null); return; }
    setSpeakingId(m.id);
    speak(m.content, () => setSpeakingId((cur) => (cur === m.id ? null : cur)));
  }

  function flushNotes() {
    // Save immediately if an edit is still waiting on its debounce timer.
    if (!active || !notesTimer.current || !notesDirty.current) return;
    clearTimeout(notesTimer.current);
    notesTimer.current = null;
    api(`/career-coach/sessions/${active.id}/notes`, { method: "PUT", body: JSON.stringify({ content: notes }) }).catch(() => {});
  }

  function closeSession() {
    flushNotes();
    dictation.current?.stop();
    stopSpeaking();
    setSpeakingId(null);
    setActive(null);
  }

  async function start() {
    if (starting || role.trim().length < 2) return;
    setStarting(true);
    setError("");
    try {
      const r = await api<{ session: CareerCoachSession; opening_message: CareerCoachMessage }>(
        "/career-coach/sessions",
        { method: "POST", body: JSON.stringify({ session_type: type, target_role: role.trim(), topic: topic.trim(), learning_style: learningStyle, voice: readAloud }) }
      );
      setSessions((s) => [r.session, ...s]);
      setActive(r.session);
      setMessages([r.opening_message]);
      setTopic("");
      if (readAloud) { setSpeakingId(r.opening_message.id); speak(r.opening_message.content, () => setSpeakingId(null)); }
    } catch (err: any) {
      setError(err.message || "Couldn't start a session — try again.");
    } finally {
      setStarting(false);
    }
  }

  async function open(s: CareerCoachSession) {
    flushNotes();
    setError("");
    setActive(s);
    setMessages([]);
    try {
      setMessages(await api<CareerCoachMessage[]>(`/career-coach/sessions/${s.id}/messages`));
    } catch (err: any) {
      setError(err.message || "Couldn't load that session.");
      setActive(null);
    }
  }

  async function send(override?: { text: string; style: "visual" | "stepbystep" | "story" | "handson" }) {
    const text = override ? override.text : input;
    if (!text.trim() || sending || !active) return;
    dictation.current?.stop();
    if (!override) setInput("");
    setSending(true);
    setError("");
    setMessages((m) => [...m, { id: -Date.now(), role: "user", content: text, created_at: new Date().toISOString() }]);
    try {
      const reply = await api<CareerCoachMessage>(`/career-coach/sessions/${active.id}/messages`, {
        method: "POST", body: JSON.stringify(override ? { message: text, style: override.style, voice: readAloud } : { message: text, voice: readAloud }),
      });
      setMessages((m) => [...m, reply]);
      if (readAloud) { setSpeakingId(reply.id); speak(reply.content, () => setSpeakingId(null)); }
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
    dictation.current?.stop();
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

  const lastCoachId = [...messages].reverse().find((m) => m.role === "assistant")?.id;

  const completedSessions = sessions.filter((s) => s.status === "completed");
  const scoredSessions = completedSessions.filter((s) => s.score !== null);
  const avgScore = scoredSessions.length
    ? Math.round(scoredSessions.reduce((sum, s) => sum + (s.score as number), 0) / scoredSessions.length)
    : null;
  const selectedStyle = LEARNING_STYLES.find((l) => l.value === learningStyle);
  const activeStyleLabel = LEARNING_STYLES.find((l) => l.value === (active?.learning_style ?? "auto"))?.label ?? "Let the coach adapt";

  const sessionList = (
    <div className="card">
      <h3 className="cc-list-title">Past sessions</h3>
      {!loaded ? (
        <p className="cc-empty">Loading…</p>
      ) : sessions.length === 0 ? (
        <p className="cc-empty">No sessions yet. Your first one will show up here with its score.</p>
      ) : (
        sessions.map((s) => (
          <button
            key={s.id} type="button"
            className={`cc-session ${active?.id === s.id ? "is-active" : ""}`}
            onClick={() => open(s)}
          >
            <span>
              <span className="cc-session-topic">{s.topic}</span>
              <span className="cc-session-meta">{typeLabel(s.session_type)} · {s.target_role}</span>
              <span className="cc-session-meta">{formatWhen(s.created_at)}</span>
            </span>
            {s.status === "completed" ? <ScoreBadge score={s.score} /> : <span className="hint">In progress</span>}
          </button>
        ))
      )}
    </div>
  );

  return (
    <div>
      <div className="cc-head">
        <h1>Career Coach</h1>
        <p>
          Practice for any role you&apos;re aiming for with drills, real tasks, mock interviews and resume
          coaching, and get honest scores and feedback. The coach uses your resume for context
          (<Link href="/dashboard/resume">edit it here</Link>) and never invents experience for you.
        </p>
      </div>

      {error && <div className="cc-error" role="alert">{error}</div>}

      <div className="cc-grid">
        {/* ---------- Main column ---------- */}
        <div className="cc-col">
          {!active && (
            <div className="card" style={{ padding: "26px 28px" }}>
              <h2 className="cc-card-title">Start a session</h2>
              <p className="cc-card-sub">Choose a role and a way to practice. You can end a session any time to get your score.</p>

              <div className="cc-group">
                <label className="cc-label" htmlFor="cc-role">Role or field you&apos;re aiming for</label>
                <input
                  id="cc-role" className="cc-input cc-input-lg"
                  placeholder="For example: Data analyst, UX designer, ICU nurse"
                  value={role} maxLength={120} onChange={(e) => setRole(e.target.value)}
                />
              </div>

              <fieldset className="cc-group" style={{ border: 0, padding: 0, margin: "0 0 22px 0" }}>
                <legend className="cc-label" style={{ padding: 0 }}>How do you want to practice?</legend>
                <div className="cc-tiles">
                  {SESSION_TYPES.map((t) => (
                    <label key={t.value} className="cc-tile">
                      <input type="radio" name="cc-type" checked={type === t.value} onChange={() => setType(t.value)} />
                      <span className="cc-tile-body">
                        <strong>{t.label}</strong>
                        <span>{t.hint}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>

              <fieldset className="cc-group" style={{ border: 0, padding: 0, margin: "0 0 22px 0" }}>
                <legend className="cc-label" style={{ padding: 0 }}>How do you like to learn?</legend>
                <div className="cc-seg">
                  {LEARNING_STYLES.map((l) => (
                    <label key={l.value} className="cc-pill">
                      <input type="radio" name="cc-style" checked={learningStyle === l.value} onChange={() => setLearningStyle(l.value)} />
                      <span>{l.label}</span>
                    </label>
                  ))}
                </div>
                {selectedStyle && <p className="cc-seg-hint">{selectedStyle.hint}.</p>}
              </fieldset>

              <div className="cc-group">
                <label className="cc-label" htmlFor="cc-topic">
                  {type === "resume" ? "Section to focus on" : "Topic"} <small>(optional)</small>
                </label>
                <input
                  id="cc-topic" className="cc-input"
                  placeholder={type === "resume" ? "For example: Work experience" : "Leave blank and the coach will pick one"}
                  value={topic} maxLength={200} onChange={(e) => setTopic(e.target.value)}
                />
              </div>

              <div className="cc-start-row">
                <button className="btn btn-primary" onClick={start} disabled={starting || role.trim().length < 2}>
                  {starting ? "Starting…" : "Start session"}
                </button>
              </div>
            </div>
          )}

          {active && (
            <div className="card cc-chat">
              <div className="cc-chat-head">
                <div>
                  <h2>{active.topic}</h2>
                  <div className="cc-chat-meta">
                    {typeLabel(active.session_type)} · {active.target_role} · Started {formatWhen(active.created_at)}
                  </div>
                </div>
                <button className="btn btn-ghost btn-sm" onClick={closeSession}>Close session</button>
              </div>

              <div className="cc-chat-window" aria-live="polite">
                {messages.map((m) => (
                  <div key={m.id} className={`cc-msg ${m.role}`}>
                    {m.role === "assistant" && <span className="cc-avatar" aria-hidden>C</span>}
                    <div className="cc-bubble">
                      {m.role === "assistant" ? <CoachText text={m.content} /> : m.content}
                      {m.visual && <VisualDiagram visual={m.visual} />}
                      {m.resources && m.resources.length > 0 && (
                        <div style={{ marginTop: 6, whiteSpace: "normal" }}>
                          {m.resources.map((r) => <ResourceCard key={r.id} item={r} compact />)}
                        </div>
                      )}
                      {m.role === "assistant" && m.id === lastCoachId && active?.status === "in_progress" &&
                        active.session_type !== "interview" && !sending && messages.length > 1 && (
                        <div className="cc-tools">
                          <div className="cc-tools-label">Explain it differently</div>
                          <div className="cc-chips">
                            {REEXPLAIN.map((r) => (
                              <button key={r.style} className="btn btn-ghost btn-sm"
                                      onClick={() => send({ text: r.message, style: r.style })}>
                                {r.label}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                      {canSpeak && m.role === "assistant" && (
                        <button
                          className="btn btn-ghost btn-sm" style={{ display: "flex", marginTop: 10 }}
                          onClick={() => playMessage(m)}
                          aria-label={speakingId === m.id ? "Stop reading aloud" : "Read this aloud"}
                        >
                          {speakingId === m.id ? "■ Stop" : "▶ Listen"}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
                {sending && (
                  <div className="cc-msg assistant">
                    <span className="cc-avatar" aria-hidden>C</span>
                    <div className="cc-bubble cc-thinking">Thinking…</div>
                  </div>
                )}
                <div ref={endRef} />
              </div>

              {active.status === "completed" ? (
                <div className="cc-result">
                  <div>
                    {active.score === null ? (
                      <div className="hint">Not scored</div>
                    ) : (
                      <>
                        <div className={`cc-score ${active.score >= 80 ? "is-high" : ""}`}>
                          {active.score}<small>/ 100</small>
                        </div>
                        <div className="cc-bar" aria-hidden><div style={{ width: `${Math.max(0, Math.min(100, active.score))}%` }} /></div>
                      </>
                    )}
                    {active.completed_at && (
                      <div className="hint" style={{ marginTop: 10 }}>Finished {formatWhen(active.completed_at)}</div>
                    )}
                  </div>
                  <div>
                    <h3>Coach feedback</h3>
                    <p>{active.feedback}</p>
                  </div>
                </div>
              ) : (
                <div className="cc-composer">
                  <div className="cc-composer-row">
                    <textarea
                      className="cc-input"
                      value={input} onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
                      }}
                      rows={2}
                      aria-label="Your reply"
                      placeholder={active.session_type === "resume" ? "Paste a bullet or section to rewrite…" : "Write your reply. Press Enter to send, Shift+Enter for a new line."}
                    />
                    {canDictate && (
                      <button
                        className={`btn ${listening ? "btn-primary" : "btn-ghost"}`}
                        onClick={toggleDictation} aria-pressed={listening}
                        aria-label={listening ? "Stop dictating" : "Dictate your reply"}
                        title={listening ? "Stop dictating" : "Dictate your reply"}
                      >
                        {listening ? "● Listening…" : "🎤"}
                      </button>
                    )}
                    <button className="btn btn-primary" onClick={() => send()} disabled={sending || !input.trim()}>Send</button>
                  </div>
                  <div className="cc-composer-foot">
                    {canSpeak ? (
                      <label className="cc-check">
                        <input type="checkbox" checked={readAloud} onChange={(e) => toggleReadAloud(e.target.checked)} />
                        Read the coach&apos;s replies aloud
                      </label>
                    ) : <span />}
                    <button className="btn btn-ghost btn-sm" onClick={end} disabled={completing}>
                      {completing ? "Scoring…" : "End session and get feedback"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ---------- Side column ---------- */}
        <div className="cc-col cc-aside">
          {!active && (
            <div className="card">
              <div className="cc-stats">
                <div className="cc-stat">
                  <div className="cc-stat-value">{sessions.length}</div>
                  <div className="cc-stat-label">Sessions</div>
                </div>
                <div className="cc-stat">
                  <div className="cc-stat-value">{completedSessions.length}</div>
                  <div className="cc-stat-label">Completed</div>
                </div>
                <div className="cc-stat">
                  <div className="cc-stat-value">{avgScore ?? "–"}</div>
                  <div className="cc-stat-label">Average score</div>
                </div>
              </div>
            </div>
          )}

          {active && (
            <div className="card">
              <h3 className="cc-list-title">Session details</h3>
              <dl className="cc-dl">
                <dt>Role</dt><dd>{active.target_role}</dd>
                <dt>Practice</dt><dd>{typeLabel(active.session_type)}</dd>
                <dt>Learning style</dt><dd>{activeStyleLabel}</dd>
                <dt>Status</dt><dd>{active.status === "completed" ? "Completed" : "In progress"}</dd>
              </dl>
            </div>
          )}

          {active && shelf.length > 0 && (
            <div className="card">
              <div className="card-row" style={{ marginBottom: 4 }}>
                <h3 className="cc-list-title" style={{ margin: 0 }}>Go deeper</h3>
                <Link href="/dashboard/library" className="hint">Browse the Library</Link>
              </div>
              <p className="hint" style={{ marginTop: 0 }}>Hand-picked reading and practice for {active.target_role}.</p>
              {shelf.map((r) => <ResourceCard key={r.id} item={r} />)}
            </div>
          )}

          {active && (
            <div className="card">
              <div className="card-row" style={{ marginBottom: 6 }}>
                <h3 className="cc-list-title" style={{ margin: 0 }}>Notepad</h3>
                <span className="cc-notes-state" aria-live="polite">
                  {notesState === "saving" && "Saving…"}
                  {notesState === "saved" && "Saved"}
                  {notesState === "error" && "Couldn't save. Keep this tab open and keep typing to retry."}
                </span>
              </div>
              <p className="hint" style={{ marginTop: 0 }}>
                Your own space for answers worth keeping, stories to reuse and things to study. Only you can
                see it, and the coach doesn&apos;t read it.
              </p>
              <textarea
                className="cc-input" aria-label="Notepad"
                value={notes} onChange={(e) => onNotesChange(e.target.value)} maxLength={20000}
                placeholder="Takeaways, follow-ups, phrases to practice…"
                style={{ minHeight: 180 }}
              />
            </div>
          )}

          {sessionList}
        </div>
      </div>
    </div>
  );
}


// The coach sometimes writes **bold** and --- rules. Show them as real
// formatting instead of raw symbols.
function CoachText({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <>
      {lines.map((line, i) => {
        const last = i === lines.length - 1;
        if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
          return <span key={i} className="cc-rule" aria-hidden />;
        }
        const parts = line.split(/\*\*(.+?)\*\*/g);
        return (
          <span key={i}>
            {parts.map((part, j) => (j % 2 === 1 ? <strong key={j}>{part}</strong> : part))}
            {!last && "\n"}
          </span>
        );
      })}
    </>
  );
}
