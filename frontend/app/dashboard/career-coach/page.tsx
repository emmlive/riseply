"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, CareerCoachMessage, CareerCoachSession, CareerCoachSessionType, LearningStyle, LibraryItem } from "@/lib/api";
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
        { method: "POST", body: JSON.stringify({ session_type: type, target_role: role.trim(), topic: topic.trim(), learning_style: learningStyle }) }
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
        method: "POST", body: JSON.stringify(override ? { message: text, style: override.style } : { message: text }),
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
          <div style={{ marginBottom: 12 }}>
            <label className="hint" htmlFor="cc-style" style={{ display: "block", marginBottom: 4 }}>How do you like to learn?</label>
            <select id="cc-style" value={learningStyle} onChange={(e) => setLearningStyle(e.target.value as LearningStyle)}>
              {LEARNING_STYLES.map((l) => <option key={l.value} value={l.value}>{l.label} — {l.hint}</option>)}
            </select>
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
            <button className="btn btn-ghost btn-sm" onClick={closeSession}>Close</button>
          </div>

          <div className="chat-window" style={{ maxHeight: 420, padding: "12px 0" }}>
            {messages.map((m) => (
              <div key={m.id} className={`chat-bubble ${m.role}`} style={{ whiteSpace: "pre-wrap" }}>
                {m.content}
                {m.visual && <VisualDiagram visual={m.visual} />}
                {m.resources && m.resources.length > 0 && (
                  <div style={{ marginTop: 6 }}>
                    {m.resources.map((r) => <ResourceCard key={r.id} item={r} compact />)}
                  </div>
                )}
                {m.role === "assistant" && m.id === lastCoachId && active?.status === "in_progress" &&
                  active.session_type !== "interview" && !sending && messages.length > 1 && (
                  <div style={{ marginTop: 8 }}>
                    <div className="hint" style={{ marginBottom: 4 }}>Explain it differently:</div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
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
                    className="btn btn-ghost btn-sm" style={{ display: "block", marginTop: 6 }}
                    onClick={() => playMessage(m)}
                    aria-label={speakingId === m.id ? "Stop reading aloud" : "Read this aloud"}
                  >
                    {speakingId === m.id ? "■ Stop" : "▶ Listen"}
                  </button>
                )}
              </div>
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
              {canSpeak && (
                <label className="hint" style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8, cursor: "pointer" }}>
                  <input type="checkbox" checked={readAloud} onChange={(e) => toggleReadAloud(e.target.checked)} />
                  Read the coach&apos;s replies aloud
                </label>
              )}
              <button className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={end} disabled={completing}>
                {completing ? "Scoring…" : "End session & get feedback"}
              </button>
            </>
          )}
        </div>
      )}

      {active && shelf.length > 0 && (
        <div className="card">
          <div className="card-row" style={{ marginBottom: 4 }}>
            <h3 style={{ margin: 0 }}>Go deeper</h3>
            <Link href="/dashboard/library" className="hint">Browse the Library</Link>
          </div>
          <p className="hint" style={{ marginTop: 0 }}>Hand-picked reading and practice for {active.target_role}.</p>
          {shelf.map((r) => <ResourceCard key={r.id} item={r} />)}
        </div>
      )}

      {active && (
        <div className="card">
          <div className="card-row" style={{ marginBottom: 6 }}>
            <h3 style={{ margin: 0 }}>Notepad</h3>
            <span className="hint">
              {notesState === "saving" && "Saving…"}
              {notesState === "saved" && "Saved"}
              {notesState === "error" && "Couldn't save — keep this tab open and try typing again"}
            </span>
          </div>
          <p className="hint" style={{ marginTop: 0 }}>
            Your own space for answers worth keeping, stories to reuse, and things to study. Only you see
            it, and the coach doesn&apos;t read it.
          </p>
          <textarea
            value={notes} onChange={(e) => onNotesChange(e.target.value)} maxLength={20000}
            placeholder="Jot down takeaways, follow-ups, phrases to practice…"
            style={{ width: "100%", minHeight: 140 }}
          />
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
