"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, CoachReplyRating, CareerCoachMessage, CareerCoachSession, CareerCoachSessionType, formatWhen, LearningStyle, LibraryItem } from "@/lib/api";
import ResourceCard from "@/components/ResourceCard";
import VisualDiagram from "@/components/VisualDiagram";
import SaveToStudy, { StudyDraft } from "@/components/SaveToStudy";
import VoicePicker from "@/components/VoicePicker";
import { ReadinessCard } from "@/components/Readiness";
import Fold from "@/components/Fold";
import MemoryCue, { CueKey } from "@/components/MemoryCue";
import { CueStyle, cueNoteLine, cuesToNoteText, cuesUsed, parseCueLine } from "@/lib/cues";
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
  // Thumbs on coach replies: message id -> helpful. "why" is the open
  // thumbs-down note box (one at a time).
  const [ratings, setRatings] = useState<Record<number, boolean>>({});
  const [whyId, setWhyId] = useState<number | null>(null);
  const [whyText, setWhyText] = useState("");

  const [role, setRole] = useState("");
  const [type, setType] = useState<CareerCoachSessionType>("drill");
  const [topic, setTopic] = useState("");
  const [learningStyle, setLearningStyle] = useState<LearningStyle>("auto");
  const [starting, setStarting] = useState(false);
  const winRef = useRef<HTMLDivElement>(null);

  // Voice: dictation fills the reply box (you review it, then send);
  // read-aloud speaks the coach's replies. Both use on-device browser
  // APIs and are hidden where unsupported. Support is detected after
  // mount so server and client render the same markup.
  const [canDictate, setCanDictate] = useState(false);
  const [canSpeak, setCanSpeak] = useState(false);
  const [listening, setListening] = useState(false);
  const [readAloud, setReadAloud] = useState(false);
  const [saveDraft, setSaveDraft] = useState<StudyDraft | null>(null);
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
    // Scroll the conversation itself, not the whole page, so the header and
    // side column stay where they are.
    const el = winRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
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

  useEffect(() => {
    setRatings({});
    setWhyId(null);
    if (!active) return;
    let cancelled = false;
    api<CoachReplyRating[]>(`/feedback/coach-replies?session_id=${active.id}`)
      .then((rows) => {
        if (cancelled) return;
        const map: Record<number, boolean> = {};
        rows.forEach((r) => { map[r.message_id] = r.helpful; });
        setRatings(map);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [active?.id]);

  async function rateReply(m: CareerCoachMessage, helpful: boolean, note = "") {
    const prev = ratings[m.id];
    setRatings((r) => ({ ...r, [m.id]: helpful }));
    setWhyId(helpful || note ? null : m.id);
    setWhyText("");
    try {
      await api("/feedback/coach-reply", { method: "PUT", body: JSON.stringify({ message_id: m.id, helpful, note: note || null }) });
    } catch {
      setRatings((r) => {
        const next = { ...r };
        if (prev === undefined) delete next[m.id]; else next[m.id] = prev;
        return next;
      });
      setWhyId(null);
      setError("Couldn't save your rating. Try again.");
    }
  }

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

  function sessionLabel(s: CareerCoachSession) {
    return `${typeLabel(s.session_type)} · ${s.target_role}`;
  }

  function saveNotepad() {
    if (!active || !notes.trim()) return;
    flushNotes();
    setSaveDraft({ title: `${active.topic} notes`, content: notes.trim(), source: "notepad", sourceLabel: sessionLabel(active), sessionId: active.id });
  }

  // "Save to my notes" on a memory cue: the line goes straight into the
  // notepad below, object included, and autosaves like anything typed there.
  function saveCue(style: CueStyle, text: string) {
    if (!active) return;
    const line = cueNoteLine(style, text);
    if (notes.includes(line)) return;
    const next = notes.trim() ? `${notes.replace(/\s+$/, "")}\n\n${line}` : line;
    if (next.length > 20000) { setError("Your notepad is full. Clear some space, then save this again."); return; }
    onNotesChange(next);
  }

  function saveReply(m: CareerCoachMessage) {
    if (!active) return;
    setSaveDraft({ title: active.topic, content: cuesToNoteText(m.content).replace(/\*\*/g, "").replace(/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/gm, "").replace(/\n{3,}/g, "\n\n").trim(), source: "coach_reply", sourceLabel: sessionLabel(active), sessionId: active.id });
  }

  function saveFeedback() {
    if (!active || !active.feedback) return;
    setSaveDraft({
      title: `${active.topic} feedback`,
      content: `${active.score !== null ? `Score: ${active.score}/100\n\n` : ""}${active.feedback}`,
      source: "feedback", sourceLabel: sessionLabel(active), sessionId: active.id,
    });
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

  // "Practice this now" on the readiness card: set up the start form for the
  // suggested role and session type, ready to press Start.
  function startPractice(roleName: string, sessionType: CareerCoachSessionType) {
    closeSession();
    setRole(roleName);
    setType(sessionType);
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
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
    // On a phone the session list sits below the chat; bring the chat into view.
    if (typeof window !== "undefined" && window.innerWidth <= 1040) window.scrollTo({ top: 0, behavior: "smooth" });
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

  const usedCues = cuesUsed(messages.filter((m) => m.role === "assistant").map((m) => m.content));
  const lastCoachId = [...messages].reverse().find((m) => m.role === "assistant")?.id;

  const completedSessions = sessions.filter((s) => s.status === "completed");
  const scoredSessions = completedSessions.filter((s) => s.score !== null);
  const avgScore = scoredSessions.length
    ? Math.round(scoredSessions.reduce((sum, s) => sum + (s.score as number), 0) / scoredSessions.length)
    : null;
  const selectedStyle = LEARNING_STYLES.find((l) => l.value === learningStyle);
  const activeStyleLabel = LEARNING_STYLES.find((l) => l.value === (active?.learning_style ?? "auto"))?.label ?? "Let the coach adapt";

  const sessionList = (
    <Fold id="sessions" title="Past sessions" defaultOpen={!active} note={sessions.length ? `${sessions.length}` : undefined}>
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
    </Fold>
  );

  return (
    <div>
      <div className={`cc-head ${active ? "is-compact" : ""}`}>
        <h1>Career Coach</h1>
        <p>
          Practice for any role you&apos;re aiming for with drills, real tasks, mock interviews and resume
          coaching, and get honest scores and feedback. The coach uses your resume for context
          (<Link href="/dashboard/resume">edit it here</Link>) and never invents experience for you.{" "}
          <Link href="/dashboard/career-coach/study">Open your study folders</Link> to review notes you&apos;ve saved.
        </p>
        {active && (
          <p className="cc-head-links">
            <Link href="/dashboard/resume">Edit resume</Link>
            <Link href="/dashboard/career-coach/study">Study folders</Link>
          </p>
        )}
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
            <div className={`card cc-chat ${active.status !== "completed" ? "is-live" : ""}`}>
              <div className="cc-chat-head">
                <div>
                  <h2>{active.topic}</h2>
                  <div className="cc-chat-meta">
                    {typeLabel(active.session_type)} · {active.target_role} · Started {formatWhen(active.created_at)}
                  </div>
                </div>
                <button className="btn btn-ghost btn-sm" onClick={closeSession}>Close session</button>
              </div>

              <CueKey used={usedCues} />
              <div className="cc-chat-window" aria-live="polite" ref={winRef}>
                {messages.map((m) => (
                  <div key={m.id} className={`cc-msg ${m.role}`}>
                    {m.role === "assistant" && <span className="cc-avatar" aria-hidden>C</span>}
                    <div className="cc-bubble">
                      {m.role === "assistant" ? <CoachText text={m.content} notes={notes} onSaveCue={saveCue} /> : m.content}
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
                      {m.role === "assistant" && (canSpeak || m.id > 0) && (
                        <div className="cc-reply-actions">
                          {canSpeak && (
                            <button
                              className="btn btn-ghost btn-sm"
                              onClick={() => playMessage(m)}
                              aria-label={speakingId === m.id ? "Stop reading aloud" : "Read this aloud"}
                            >
                              {speakingId === m.id ? "■ Stop" : "▶ Listen"}
                            </button>
                          )}
                          {m.id > 0 && (
                            <button className="btn btn-ghost btn-sm"
                                    onClick={() => saveReply(m)} aria-label="Save this reply to a study folder">
                              Save to study folder
                            </button>
                          )}
                          {m.id > 0 && (
                            <>
                              <button className="btn btn-ghost btn-sm cc-thumb" aria-pressed={ratings[m.id] === true}
                                      aria-label="This reply helped" onClick={() => rateReply(m, true)}>👍</button>
                              <button className="btn btn-ghost btn-sm cc-thumb down" aria-pressed={ratings[m.id] === false}
                                      aria-label="This reply didn't help" onClick={() => rateReply(m, false)}>👎</button>
                            </>
                          )}
                          {whyId === m.id && (
                            <div className="cc-why">
                              <label className="hint" htmlFor={`why-${m.id}`}>What went wrong? (optional)</label>
                              <textarea id={`why-${m.id}`} className="cc-input" rows={2} maxLength={1000} value={whyText}
                                        onChange={(e) => setWhyText(e.target.value)} />
                              <div className="cc-why-row">
                                <button className="btn btn-primary btn-sm" disabled={!whyText.trim()}
                                        onClick={() => rateReply(m, false, whyText.trim())}>Send</button>
                                <button className="btn btn-ghost btn-sm" onClick={() => setWhyId(null)}>Skip</button>
                              </div>
                            </div>
                          )}
                        </div>
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
                    <button className="btn btn-ghost btn-sm" style={{ marginTop: 10 }} onClick={saveFeedback}>
                      Save to study folder
                    </button>
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
            <Fold id="details" title="Session details" defaultOpen={false} note={typeLabel(active.session_type)}>
              <dl className="cc-dl">
                <dt>Role</dt><dd>{active.target_role}</dd>
                <dt>Practice</dt><dd>{typeLabel(active.session_type)}</dd>
                <dt>Learning style</dt><dd>{activeStyleLabel}</dd>
                <dt>Status</dt><dd>{active.status === "completed" ? "Completed" : "In progress"}</dd>
              </dl>
            </Fold>
          )}

          {active && shelf.length > 0 && (
            <Fold id="deeper" title="Go deeper" defaultOpen={false} note={`${shelf.length} pick${shelf.length === 1 ? "" : "s"}`}>
              <p className="hint" style={{ marginTop: 0 }}>
                Hand-picked reading and practice for {active.target_role}.{" "}
                <Link href="/dashboard/library">Browse the Library</Link>
              </p>
              {shelf.map((r) => <ResourceCard key={r.id} item={r} />)}
            </Fold>
          )}

          <ReadinessCard
            activeRole={active?.target_role}
            refreshKey={`${active?.id ?? 0}-${active?.status ?? ""}-${active?.score ?? ""}`}
            onPractice={startPractice}
          />

          {active && (
            <Fold id="notepad" title="Notepad" defaultOpen
              aside={
                <span className="cc-notes-state" aria-live="polite">
                  {notesState === "saving" && "Saving…"}
                  {notesState === "saved" && "Saved"}
                  {notesState === "error" && "Couldn't save"}
                </span>
              }>
              {notesState === "error" && <p className="cc-error" role="alert">Couldn&apos;t save. Keep this tab open and keep typing to retry.</p>}
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
              <div className="card-row" style={{ marginTop: 10, alignItems: "center", gap: 10 }}>
                <button className="btn btn-ghost btn-sm" onClick={saveNotepad} disabled={!notes.trim()}>
                  Save to study folder
                </button>
                <Link href="/dashboard/career-coach/study" className="hint">Study folders</Link>
              </div>
              <p className="hint" style={{ marginBottom: 0 }}>
                This notepad is kept with the session. Saving to a folder files a copy you can review any time.
              </p>
            </Fold>
          )}

          {canSpeak && <VoicePicker />}

          {sessionList}
        </div>
      </div>

      {saveDraft && <SaveToStudy draft={saveDraft} onClose={() => setSaveDraft(null)} />}
    </div>
  );
}


// The coach sometimes writes **bold** and --- rules. Show them as real
// formatting instead of raw symbols.
function CoachText({ text, notes, onSaveCue }: {
  text: string; notes: string; onSaveCue: (style: CueStyle, text: string) => void;
}) {
  const lines = text.split("\n");
  return (
    <>
      {lines.map((line, i) => {
        const last = i === lines.length - 1;
        if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
          return <span key={i} className="cc-rule" aria-hidden />;
        }
        const cue = parseCueLine(line);
        if (cue) {
          return (
            <MemoryCue key={i} style={cue.style} text={cue.text}
              saved={notes.includes(cueNoteLine(cue.style, cue.text))}
              onSave={() => onSaveCue(cue.style, cue.text)} />
          );
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
