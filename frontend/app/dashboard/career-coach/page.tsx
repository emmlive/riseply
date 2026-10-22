"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { api, CoachCourse, CoachCourseListItem, CoachReplyRating, CareerCoachMessage, CareerCoachSession, CareerCoachSessionType, CareerCoachVisualKind, formatWhen, LearningStyle, LibraryItem, QuizOptions } from "@/lib/api";
import ResourceCard from "@/components/ResourceCard";
import VisualDiagram from "@/components/VisualDiagram";
import { focusIndex } from "@/lib/whiteboard";
import { heardTail, parseInterruption, restAfterWait, sentenceStart } from "@/lib/interrupt";
import CoachVideos from "@/components/CoachVideos";
import CoachNotebook from "@/components/CoachNotebook";
import SaveToStudy, { StudyDraft } from "@/components/SaveToStudy";
import VoicePicker from "@/components/VoicePicker";
import CoursePanel from "@/components/CoursePanel";
import ModuleRecap from "@/components/ModuleRecap";
import DiagramPad from "@/components/DiagramPad";
import WorkArea from "@/components/WorkArea";
import SessionClock from "@/components/SessionClock";
import { minutesText, useSessionClock } from "@/lib/sessionClock";
import { ReadinessCard } from "@/components/Readiness";
import Fold from "@/components/Fold";
import MemoryCue, { CueKey } from "@/components/MemoryCue";
import { CueStyle, cueNoteLine, cuesToNoteText, cuesUsed } from "@/lib/cues";
import {
  Dictation, dictationSupported, speak, speechSynthesisSupported, spokenWordList, startDictation, stopSpeaking,
} from "@/lib/speech";
import { alignSpoken, currentWordTable, layoutCoachText } from "@/lib/readalong";
import { analyzeDelivery, clock, countWords, Delivery, deliveryLabel, paceNote } from "@/lib/delivery";

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
  { value: "upskill", label: "Upskilling", hint: "Already working in your field? Find the next skill worth adding and build it with practice" },
  { value: "negotiation", label: "Salary negotiation", hint: "Got an offer, or about to? Negotiate with a recruiter in a safe role-play, then get scored" },
  { value: "leadership", label: "How leaders think", hint: "Moving into management or an executive role? Practice the decisions leaders face and learn how they think" },
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

// "Draw it as..." -- the person picks the kind of picture the coach draws.
const DRAW_AS: { kind: CareerCoachVisualKind | ""; label: string }[] = [
  { kind: "flow", label: "Steps in order" },
  { kind: "cycle", label: "A cycle that repeats" },
  { kind: "compare", label: "A comparison table" },
  { kind: "map", label: "A concept map" },
  { kind: "matrix", label: "A 2×2 grid" },
  { kind: "layers", label: "Layers or a pyramid" },
  { kind: "chart", label: "A bar chart" },
  { kind: "", label: "Let the coach choose" },
];

// Role-plays where the coach stays in character (no teaching cards mid-scene).
const IN_CHARACTER: string[] = ["interview", "negotiation"];
const LESSON_TYPES: string[] = ["drill", "walkthrough", "upskill", "leadership"];

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
  const [timeLimit, setTimeLimit] = useState(0);   // minutes chosen on the start form, 0 = no limit
  // "Quiz me first" on saved study notes: "" = no, "all", or a folder id.
  const [quizPick, setQuizPick] = useState("");
  const [quizOptions, setQuizOptions] = useState<QuizOptions | null>(null);
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
  // Courses: the syllabus being viewed, the person's course list, and the course behind the open lesson.
  const [course, setCourse] = useState<CoachCourse | null>(null);
  const [courses, setCourses] = useState<CoachCourseListItem[]>([]);
  const [lessonCourse, setLessonCourse] = useState<CoachCourse | null>(null);
  const [busyModule, setBusyModule] = useState("");
  const [padOpen, setPadOpen] = useState(false);
  const [workOpen, setWorkOpen] = useState(false);
  const [speakingId, setSpeakingId] = useState<number | null>(null);
  // Which spoken word the voice is on (-1 = not started), for the read-along highlight.
  const [spokenAt, setSpokenAt] = useState(-1);
  // A new text reply types itself in; this is how many of its words are showing.
  const [reveal, setReveal] = useState<{ id: number; count: number } | null>(null);
  const revealTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const speakingRef = useRef<number | null>(null);
  speakingRef.current = speakingId;
  const dictation = useRef<Dictation | null>(null);
  const dictationBase = useRef("");
  // Voice interview: the coach asks aloud, the mic opens by itself, and the
  // person presses Done to send. Delivery (pace, length, fillers) is measured
  // from the dictated text and the time taken.
  const [voiceMode, setVoiceMode] = useState(false);
  const voiceModeRef = useRef(false);
  // Interrupting the coach (lib/interrupt.ts): "Wait" and "Back" buttons always,
  // and, when switched on, the mic listens for "wait" / "go back" while the coach talks.
  const [interruptOn, setInterruptOn] = useState(false);
  const interruptRef = useRef(false);
  const [armed, setArmed] = useState(false);          // mic open, listening for a command
  const [capturing, setCapturing] = useState(false);  // coach stopped; taking the person's question
  const spokenAtRef = useRef(-1);
  spokenAtRef.current = spokenAt;
  const speakingMsg = useRef<CareerCoachMessage | null>(null);
  const pendingInterrupt = useRef<{ heard: string } | null>(null);
  const captureTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const interruptListening = useRef(false);   // the open mic is the "wait / go back" listener
  const composerEl = useRef<HTMLTextAreaElement>(null);
  const [elapsed, setElapsed] = useState(0);
  const answerStart = useRef<number | null>(null);
  const userStopped = useRef(false);
  const restarts = useRef(0);
  const inputRef = useRef("");

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
    if (!el) return;
    // While the coach reads its newest reply aloud, the highlight leads the
    // scrolling; jumping to the bottom would fight it.
    const last = messages[messages.length - 1];
    if (speakingRef.current !== null && last && last.id === speakingRef.current) return;
    el.scrollTo({ top: el.scrollHeight, behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, [messages, sending]);

  // Keep the newest line in view as a reply types itself in.
  useEffect(() => {
    const el = winRef.current;
    if (el && reveal) el.scrollTop = el.scrollHeight;
  }, [reveal?.count]);

  useEffect(() => { if (speakingId === null) setSpokenAt(-1); }, [speakingId]);
  useEffect(() => {
    refreshCourses();
    if (typeof window === "undefined") return;
    const id = Number(new URLSearchParams(window.location.search).get("course"));
    if (id > 0) loadCourse(id).then((c) => { if (c) setCourse(c); });
  }, []);

  useEffect(() => {
    api<QuizOptions>("/career-coach/study/quiz-options").then(setQuizOptions).catch(() => setQuizOptions(null));
  }, []);

  useEffect(() => {
    setCanDictate(dictationSupported());
    setCanSpeak(speechSynthesisSupported());
    try {
      setReadAloud(localStorage.getItem("cc-read-aloud") === "1");
    } catch { /* storage unavailable -- default off */ }
    try { const v = localStorage.getItem("cc-voice-interview") === "1"; setVoiceMode(v); voiceModeRef.current = v; } catch { /* default off */ }
    try { const t = Number(localStorage.getItem("cc-time-limit")); if ([0, 15, 30, 45, 60, 90].includes(t)) setTimeLimit(t); } catch { /* default none */ }
    try { const v = localStorage.getItem("cc-interrupt") === "1"; setInterruptOn(v); interruptRef.current = v; } catch { /* default off */ }
    return () => { if (captureTimer.current) clearTimeout(captureTimer.current); voiceModeRef.current = false; userStopped.current = true; dictation.current?.stop(); stopSpeaking(); stopReveal(); };
  }, []);

  useEffect(() => { inputRef.current = input; }, [input]);

  // Ticks the answer timer while the mic is open in a voice interview.
  useEffect(() => {
    if (!voiceMode || !listening) return;
    const t = setInterval(() => setElapsed(answerStart.current ? (Date.now() - answerStart.current) / 1000 : 0), 500);
    return () => clearInterval(t);
  }, [voiceMode, listening]);

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

  function stopDictation() {
    userStopped.current = true;
    dictation.current?.stop();
  }

  function beginDictation(): boolean {
    stopSpeaking();
    setSpeakingId(null);
    dictationBase.current = inputRef.current.trim() ? inputRef.current.trimEnd() + " " : "";
    userStopped.current = false;
    if (answerStart.current === null) { answerStart.current = Date.now(); setElapsed(0); }
    const d = startDictation(
      (text) => setInput(dictationBase.current + text),
      (err) => {
        setListening(false); dictation.current = null;
        if (err) { setError(err); return; }
        // Browsers end dictation after a pause. In a voice interview keep
        // listening until the person presses Done.
        if (voiceModeRef.current && !userStopped.current && answerStart.current !== null && restarts.current < 30) {
          restarts.current += 1;
          setTimeout(() => { if (voiceModeRef.current && !userStopped.current && !dictation.current) beginDictation(); }, 250);
        }
      },
    );
    if (!d) { setError("Dictation isn't available in this browser — you can type instead."); return false; }
    dictation.current = d;
    setListening(true);
    return true;
  }

  function toggleDictation() {
    if (listening) { stopDictation(); return; }
    beginDictation();
  }

  function toggleVoiceMode(on: boolean) {
    setVoiceMode(on);
    voiceModeRef.current = on;
    try { localStorage.setItem("cc-voice-interview", on ? "1" : "0"); } catch { /* ignore */ }
    if (on && !readAloud) toggleReadAloud(true);
    if (!on) stopDictation();
  }

  // Sends the spoken answer with its delivery numbers.
  async function finishAnswer() {
    if (!active || sending) return;
    const secs = answerStart.current ? (Date.now() - answerStart.current) / 1000 : 0;
    stopDictation();
    await new Promise((r) => setTimeout(r, 450));   // let the last words arrive
    const text = inputRef.current.trim();
    if (!text) { answerStart.current = null; setError("I didn't catch an answer. Try again, or type it."); return; }
    send(undefined, analyzeDelivery(text, secs));
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

  function noteText(text: string) {
    return cuesToNoteText(text).replace(/\*\*/g, "").replace(/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/gm, "").replace(/\n{3,}/g, "\n\n").trim();
  }

  // Course lessons are filed under their module, so notes sort themselves.
  function noteLabel(a: CareerCoachSession) {
    const mods = lessonCourse?.modules ?? [];
    const idx = a.course_id ? mods.findIndex((m) => m.id === a.module_id) : -1;
    return idx >= 0 && lessonCourse ? `Course · ${lessonCourse.title} · Module ${idx + 1}` : sessionLabel(a);
  }

  function saveReply(m: CareerCoachMessage) {
    if (!active) return;
    setSaveDraft({ title: active.topic, content: noteText(m.content), source: "coach_reply", sourceLabel: noteLabel(active), sessionId: active.id });
  }

  // Every explanation the coach gave in this lesson, as one note to study from.
  function saveLesson() {
    if (!active) return;
    const parts = messages.filter((m) => m.role === "assistant" && m.id > 0).map((m) => noteText(m.content)).filter(Boolean);
    if (!parts.length) return;
    setSaveDraft({ title: `${active.topic}: lesson notes`, content: parts.join("\n\n---\n\n").slice(0, 20000), source: "coach_reply", sourceLabel: noteLabel(active), sessionId: active.id });
  }

  function saveFeedback() {
    if (!active || !active.feedback) return;
    setSaveDraft({
      title: `${active.topic} feedback`,
      content: `${active.score !== null ? `Score: ${active.score}/100\n\n` : ""}${active.feedback}`,
      source: "feedback", sourceLabel: sessionLabel(active), sessionId: active.id,
    });
  }

  function startSpeaking(m: CareerCoachMessage, thenListen = false, fromWord = 0) {
    stopReveal();
    setSpeakingId(m.id);
    setSpokenAt(fromWord > 0 ? fromWord : -1);
    speakingMsg.current = m;
    // Replaying from the middle: speak only the words from there, and count from there.
    const text = fromWord > 0 ? spokenWordList(m.content).slice(fromWord).join(" ") : m.content;
    speak(
      text,
      () => {
        setSpeakingId((cur) => (cur === m.id ? null : cur));
        disarmInterrupt();
        // Voice interview: when the question has been asked, open the mic.
        if (thenListen && voiceModeRef.current) beginDictation();
      },
      (msg) => setError(msg),
      (i) => setSpokenAt(fromWord + i),
    );
    if (!thenListen) armInterrupt(m);
  }

  // ---- Interrupting the coach -------------------------------------------
  function clearCaptureTimer() {
    if (captureTimer.current) { clearTimeout(captureTimer.current); captureTimer.current = null; }
  }

  function disarmInterrupt() {
    setArmed(false);
    if (dictation.current && !userStopped.current && interruptListening.current) {
      interruptListening.current = false;
      userStopped.current = true;
      dictation.current.stop();
    }
  }

  // The person is talking over the coach: gather their words, and send them
  // once they pause (or stop waiting if nothing comes).
  function captureText(rest: string) {
    setInput(rest);
    clearCaptureTimer();
    const words = rest.trim().split(/\s+/).filter(Boolean).length;
    captureTimer.current = setTimeout(() => {
      captureTimer.current = null;
      stopDictation();
      setCapturing(false);
      if (words >= 1) send();
      else pendingInterrupt.current = null;   // said only "wait" and nothing followed
    }, words >= 2 ? 1600 : words === 1 ? 2200 : 8000);
  }

  function beginCapture(initial = "") {
    interruptListening.current = false;
    setCapturing(true);
    setInput(initial);
    captureText(initial);
    if (!canDictate) { composerEl.current?.focus(); return; }
    userStopped.current = false;
    const base = initial ? initial + " " : "";
    const d: Dictation | null = startDictation(
      (text) => captureText(base + text),
      (err) => {
        setListening(false);
        if (d && dictation.current === d) dictation.current = null;
        if (err) setError(err);
      },
    );
    if (!d) { composerEl.current?.focus(); return; }
    dictation.current = d;
    setListening(true);
  }

  function cancelCapture() {
    clearCaptureTimer();
    stopDictation();
    setCapturing(false);
    setInput("");
    pendingInterrupt.current = null;
  }

  function replayFromSentence() {
    const m = speakingMsg.current;
    if (!m) return;
    const words = spokenWordList(m.content);
    startSpeaking(m, false, sentenceStart(words, Math.max(0, spokenAtRef.current)));
  }

  // The "Wait" button (always works, no microphone needed to stop the coach).
  function waitNow() {
    const m = speakingMsg.current;
    if (!m) return;
    pendingInterrupt.current = { heard: heardTail(spokenWordList(m.content), spokenAtRef.current) };
    stopSpeaking();
    setSpeakingId(null);
    if (interruptListening.current && dictation.current) { userStopped.current = true; dictation.current.stop(); }
    beginCapture();
  }

  // While the coach talks, listen for "wait" or "go back" (opt in).
  function armInterrupt(m: CareerCoachMessage) {
    if (!interruptRef.current || !dictationSupported() || IN_CHARACTER.includes(active?.session_type ?? "")) return;
    const words = spokenWordList(m.content);
    let tries = 0;
    const run = () => {
      if (speakingRef.current !== m.id || !interruptRef.current) { setArmed(false); return; }
      userStopped.current = false;
      let handled = false;
      const d = startDictation(
        (text) => {
          if (handled) return;
          const r = parseInterruption(text, words, spokenAtRef.current);
          if (r.kind === "none") return;
          handled = true;
          userStopped.current = true;
          d?.stop();
          setArmed(false);
          if (r.kind === "back") { replayFromSentence(); return; }
          pendingInterrupt.current = { heard: heardTail(words, spokenAtRef.current) };
          stopSpeaking();
          setSpeakingId(null);
          // Keep what they said after "wait": the recognizer restarts for the rest.
          setTimeout(() => beginCapture(r.rest), 300);   // let the first recognizer close
        },
        () => {
          if (d && dictation.current === d) { dictation.current = null; interruptListening.current = false; }
          if (!handled && speakingRef.current === m.id && interruptRef.current && tries < 40) {
            tries += 1;
            setTimeout(run, 250);   // browsers close the mic after a quiet spell; reopen it
          } else if (!handled) setArmed(false);
        },
      );
      if (d) { dictation.current = d; interruptListening.current = true; setArmed(true); }
    };
    setTimeout(run, 400);
  }

  function toggleInterrupt(on: boolean) {
    setInterruptOn(on);
    interruptRef.current = on;
    try { localStorage.setItem("cc-interrupt", on ? "1" : "0"); } catch { /* ignore */ }
    if (!on) disarmInterrupt();
  }

  function playMessage(m: CareerCoachMessage) {
    if (speakingId === m.id) { stopSpeaking(); setSpeakingId(null); return; }
    startSpeaking(m);
  }

  function stopReveal() {
    if (revealTimer.current) { clearInterval(revealTimer.current); revealTimer.current = null; }
    setReveal(null);
  }

  // Types a new reply in word by word (about 16 words a second, and 4 seconds
  // at most however long it is). Skipped for people who ask their device for less motion.
  function startReveal(m: CareerCoachMessage) {
    stopReveal();
    if (prefersReducedMotion()) return;
    const total = layoutCoachText(m.content).words.length;
    if (total < 3) return;
    const step = Math.max(1, Math.ceil(total / 66));
    let count = 0;
    setReveal({ id: m.id, count: 0 });
    revealTimer.current = setInterval(() => {
      count += step;
      if (count >= total) stopReveal();
      else setReveal({ id: m.id, count });
    }, 60);
  }

  function flushNotes() {
    // Save immediately if an edit is still waiting on its debounce timer.
    if (!active || !notesTimer.current || !notesDirty.current) return;
    clearTimeout(notesTimer.current);
    notesTimer.current = null;
    api(`/career-coach/sessions/${active.id}/notes`, { method: "PUT", body: JSON.stringify({ content: notes }) }).catch(() => {});
  }

  // Arriving from the Skill gaps page: "?role=...&topic=...&type=upskill&style=handson"
  // fills in the start form so one press of Start begins the practice.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const q = new URLSearchParams(window.location.search);
    const r = q.get("role");
    if (!r) return;
    setRole(r.slice(0, 120));
    setTopic((q.get("topic") || "").slice(0, 200));
    const t = q.get("type");
    if (t && SESSION_TYPES.some((x) => x.value === t)) setType(t as CareerCoachSessionType);
    const st = q.get("style");
    if (st && ["auto", "visual", "handson", "story", "stepbystep"].includes(st)) setLearningStyle(st as LearningStyle);
  }, []);

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
    stopDictation();
    stopSpeaking();
    setSpeakingId(null);
    setActive(null);
  }

  async function loadCourse(id: number): Promise<CoachCourse | null> {
    try { return await api<CoachCourse>(`/career-coach/courses/${id}`); } catch { return null; }
  }

  function refreshCourses() {
    api<CoachCourseListItem[]>("/career-coach/courses").then(setCourses).catch(() => {});
  }

  async function openCourse(id: number) {
    setError("");
    const c = await loadCourse(id);
    if (!c) { setError("Couldn't open that course."); return; }
    setCourse(c);
    closeSession();
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function startModule(moduleId: string) {
    if (!course || busyModule) return;
    setBusyModule(moduleId);
    setError("");
    try {
      const r = await api<{ session: CareerCoachSession; opening_message: CareerCoachMessage }>(
        "/career-coach/sessions",
        { method: "POST", body: JSON.stringify({ session_type: "upskill", target_role: course.target_role, course_id: course.id, module_id: moduleId, learning_style: learningStyle, voice: readAloud }) }
      );
      setSessions((s) => [r.session, ...s]);
      setLessonCourse(course);
      setActive(r.session);
      setMessages([r.opening_message]);
      if (readAloud) startSpeaking(r.opening_message, false);
      else startReveal(r.opening_message);
    } catch (err: any) {
      setError(err.message || "Couldn't start that module. Try again.");
    } finally {
      setBusyModule("");
    }
  }

  async function nextModule() {
    if (!active?.course_id) return;
    const c = await loadCourse(active.course_id);
    closeSession();
    if (c) setCourse(c);
    refreshCourses();
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function start() {
    if (starting || role.trim().length < 2) return;
    setStarting(true);
    setError("");
    try {
      const r = await api<{ session: CareerCoachSession; opening_message: CareerCoachMessage }>(
        "/career-coach/sessions",
        { method: "POST", body: JSON.stringify({ session_type: type, target_role: role.trim(), topic: topic.trim(), learning_style: learningStyle, voice: readAloud, time_limit_min: timeLimit,
          ...(LESSON_TYPES.includes(type) && quizPick === "all" ? { quiz_all: true } : {}),
          ...(LESSON_TYPES.includes(type) && quizPick && quizPick !== "all" ? { quiz_folder_id: Number(quizPick) } : {}) }) }
      );
      setSessions((s) => [r.session, ...s]);
      setActive(r.session);
      setMessages([r.opening_message]);
      setTopic("");
      if (readAloud) startSpeaking(r.opening_message, voiceModeRef.current && IN_CHARACTER.includes(r.session.session_type));
      else startReveal(r.opening_message);
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
    setLessonCourse(null);
    if (s.course_id) loadCourse(s.course_id).then((c) => setLessonCourse(c));
    // On a phone the session list sits below the chat; bring the chat into view.
    if (typeof window !== "undefined" && window.innerWidth <= 1040) window.scrollTo({ top: 0, behavior: "smooth" });
    try {
      setMessages(await api<CareerCoachMessage[]>(`/career-coach/sessions/${s.id}/messages`));
    } catch (err: any) {
      setError(err.message || "Couldn't load that session.");
      setActive(null);
    }
  }

  async function send(override?: { text: string; style: "visual" | "stepbystep" | "story" | "handson"; visualKind?: CareerCoachVisualKind }, delivery?: Delivery, images?: { media_type: string; data: string }[]) {
    const text = override ? override.text : inputRef.current;
    if (!text.trim() || sending || !active) return;
    stopDictation();
    stopReveal();
    answerStart.current = null;
    restarts.current = 0;
    setElapsed(0);
    if (!override) setInput("");
    setSending(true);
    setError("");
    setMessages((m) => [...m, { id: -Date.now(), role: "user", content: text, created_at: new Date().toISOString(), ...(delivery ? { delivery } : {}) }]);
    const interruptedBody = pendingInterrupt.current;
    pendingInterrupt.current = null;
    try {
      const reply = await api<CareerCoachMessage>(`/career-coach/sessions/${active.id}/messages`, {
        method: "POST", body: JSON.stringify({ ...(images?.length ? { images } : {}), ...(sessionClock.minutesLeft !== null ? { minutes_left: sessionClock.minutesLeft } : {}), ...(override ? { message: text, style: override.style, voice: readAloud, ...(override.visualKind ? { visual_kind: override.visualKind } : {}) } : { message: text, voice: readAloud, ...(delivery ? { delivery } : {}), ...(interruptedBody ? { interrupted: true, heard_up_to: interruptedBody.heard.slice(-300) } : {}) }) }),
      });
      setMessages((m) => [...m, reply]);
      if (reply.quiz_result) {
        const quiz_result = reply.quiz_result;
        setActive((a) => (a && a.id === active.id ? { ...a, quiz_result } : a));
        setSessions((rows) => rows.map((row) => (row.id === active.id ? { ...row, quiz_result } : row)));
      }
      if (reply.lesson) {
        const lesson = reply.lesson;
        setActive((a) => (a && a.id === active.id ? { ...a, lesson } : a));
        setSessions((rows) => rows.map((row) => (row.id === active.id ? { ...row, lesson } : row)));
      }
      if (reply.recap) {
        const recap = reply.recap;
        setActive((a) => (a && a.id === active.id ? { ...a, recap } : a));
        setSessions((rows) => rows.map((row) => (row.id === active.id ? { ...row, recap } : row)));
        refreshCourses();
      }
      if (readAloud) startSpeaking(reply, voiceModeRef.current && IN_CHARACTER.includes(active.session_type));
      else startReveal(reply);
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
    stopDictation();
    setCompleting(true);
    setError("");
    try {
      const updated = await api<CareerCoachSession>(`/career-coach/sessions/${active.id}/complete`, { method: "POST" });
      setActive(updated);
      setSessions((s) => s.map((row) => (row.id === updated.id ? updated : row)));
      if (updated.course_id) refreshCourses();
    } catch (err: any) {
      setError(err.message || "Couldn't score this session — try again.");
    } finally {
      setCompleting(false);
    }
  }

  const sessionClock = useSessionClock(active, sending || completing);
  const usedCues = cuesUsed(messages.filter((m) => m.role === "assistant").map((m) => m.content));
  const lastCoachId = [...messages].reverse().find((m) => m.role === "assistant")?.id;
  const voiceReady = canDictate && canSpeak && !!active && IN_CHARACTER.includes(active.session_type) && active.status === "in_progress";

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
              <span className="cc-session-meta">{formatWhen(s.created_at)}{s.active_seconds ? ` · ${minutesText(s.active_seconds)}` : ""}</span>
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
          Practice for any role you&apos;re aiming for with drills, real tasks, mock interviews, offer negotiation and resume
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
          {!active && course && (
            <CoursePanel
              course={course} busyModule={busyModule}
              onStart={startModule}
              onOpen={(sid) => { const row = sessions.find((x) => x.id === sid); if (row) open(row); }}
              onClose={() => { setCourse(null); refreshCourses(); }}
              onDelete={async () => {
                if (!window.confirm("Delete this course? Lessons you already had stay in your past sessions.")) return;
                try { await api(`/career-coach/courses/${course.id}`, { method: "DELETE" }); setCourse(null); refreshCourses(); }
                catch (e: any) { setError(e.message || "Couldn't delete the course."); }
              }}
            />
          )}

          {!active && !course && courses.length > 0 && (
            <div className="card" style={{ padding: "18px 28px" }}>
              <h2 className="cc-card-title">Your courses</h2>
              <ul className="cp-mycourses">
                {courses.map((c) => (
                  <li key={c.id}>
                    <span><strong>{c.title}</strong><br /><span className="muted">{c.target_role} · {c.done} of {c.modules} modules done</span></span>
                    <button className="btn btn-ghost btn-sm" onClick={() => openCourse(c.id)}>{c.done ? "Continue" : "Open"}</button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!active && !course && (
            <div className="card" style={{ padding: "26px 28px" }}>
              <h2 className="cc-card-title">Start a session</h2>
              <p className="cc-card-sub">Choose a role and a way to practice. You can end a session any time to get your score.</p>

              <div className="cc-group">
                <label className="cc-label" htmlFor="cc-role">{type === "upskill" ? "Your role or field" : "Role or field you're aiming for"}</label>
                <input
                  id="cc-role" className="cc-input cc-input-lg"
                  placeholder={type === "leadership"
                    ? "For example: Engineering manager, Director of IT, CIO"
                    : type === "negotiation"
                    ? "The role you were offered, for example: Security analyst"
                    : type === "upskill"
                    ? "For example: Cybersecurity analyst, Staff accountant, ICU nurse"
                    : "For example: Data analyst, UX designer, ICU nurse"}
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
                <label className="cc-label" htmlFor="cc-time">How much time do you have? <small>(optional)</small></label>
                <select id="cc-time" value={timeLimit} onChange={(e) => { const v = Number(e.target.value); setTimeLimit(v); try { localStorage.setItem("cc-time-limit", String(v)); } catch { /* ignore */ } }}>
                  <option value={0}>No time limit</option>
                  {[15, 30, 45, 60, 90].map((m) => <option key={m} value={m}>{m} minutes</option>)}
                </select>
                <p className="cc-seg-hint">A timer keeps you on track. When time is short the coach wraps the lesson up. It never cuts you off.</p>
              </div>

              {LESSON_TYPES.includes(type) && quizOptions && quizOptions.all > 0 && (
                <div className="cc-group">
                  <label className="cc-label" htmlFor="cc-quiz">Warm up with a quiz on your saved notes <small>(optional)</small></label>
                  <select id="cc-quiz" value={quizPick} onChange={(e) => setQuizPick(e.target.value)}>
                    <option value="">No, go straight to the lesson</option>
                    <option value="all">Quiz me on all my saved notes ({quizOptions.all})</option>
                    {quizOptions.folders.map((f) => <option key={f.id} value={String(f.id)}>Folder: {f.name} ({f.count})</option>)}
                  </select>
                  {quizPick && <p className="cc-seg-hint">Up to 6 of the notes you pick are sent to the coach for this session so it can ask you 3 questions. Your other notes stay private.</p>}
                </div>
              )}

              <div className="cc-group">
                <label className="cc-label" htmlFor="cc-topic">
                  {type === "resume" ? "Section to focus on" : "Topic"} <small>(optional)</small>
                </label>
                <input
                  id="cc-topic" className="cc-input"
                  placeholder={
                    type === "resume" ? "For example: Work experience"
                    : type === "leadership" ? "For example: giving hard feedback, budgets, or your first 90 days. Leave blank and the coach will pick one"
                    : type === "negotiation" ? "For example: base salary, sign-on bonus, remote days. Leave blank and the coach will pick one"
                    : type === "upskill" ? "For example: a tool, a certification area, or a skill you want to build. Leave blank and the coach will pick one"
                    : "Leave blank and the coach will pick one"
                  }
                  value={topic} maxLength={200} onChange={(e) => setTopic(e.target.value)}
                />
              </div>

              {IN_CHARACTER.includes(type) && canDictate && canSpeak && (
                <label className="cc-check" style={{ marginBottom: 10 }}>
                  <input type="checkbox" checked={voiceMode} onChange={(e) => toggleVoiceMode(e.target.checked)} />
                  Voice mode: the {type === "negotiation" ? "recruiter" : "coach"} speaks out loud and you answer out loud (we&apos;ll measure pace and filler words)
                </label>
              )}

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
                    {active.quizzed && <> · Warm-up quiz{active.quiz_result ? `: ${active.quiz_result.replace("/", " of ")}` : ""}</>}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
                  {!IN_CHARACTER.includes(active.session_type) && messages.some((m) => m.role === "assistant" && m.id > 0) && (
                    <button className="btn btn-ghost btn-sm" onClick={saveLesson}>Save lesson notes</button>
                  )}
                  <button className="btn btn-ghost btn-sm" onClick={closeSession}>Close session</button>
                </div>
              </div>

              <SessionClock seconds={sessionClock.seconds} limitMin={sessionClock.limitMin} onLimit={sessionClock.setLimit} live={active.status === "in_progress"} />
              <CueKey used={usedCues} />
              {!IN_CHARACTER.includes(active.session_type) && <CoachVideos key={active.id} topic={active.topic} />}
              {active.course_id && lessonCourse && (() => {
                const idx = lessonCourse.modules.findIndex((m) => m.id === active.module_id);
                return idx >= 0 ? (
                  <div className="cc-module-bar">
                    <span><strong>Module {idx + 1} of {lessonCourse.modules.length}</strong> · {lessonCourse.title}</span>
                    <button className="sg-link" onClick={nextModule}>View syllabus</button>
                  </div>
                ) : null;
              })()}
              {active.lesson && active.lesson.goals.length > 0 && (
                <div className="cc-lesson" aria-label={active.course_id ? "This module's objectives" : "Today's lesson"}>
                  <strong>{active.course_id ? "This module" : "Today\u2019s lesson"}</strong>
                  <ul>
                    {active.lesson.goals.map((g, i) => {
                      const done = active.lesson!.covered.includes(i + 1);
                      return (
                        <li key={i} className={done ? "done" : ""}>
                          <span aria-hidden>{done ? "✓" : "○"}</span> {g}{done ? " (done)" : ""}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
              <div className="cc-chat-window" aria-live="polite" ref={winRef}>
                {messages.map((m) => (
                  <div key={m.id} className={`cc-msg ${m.role}`}>
                    {m.role === "assistant" && <span className={`cc-avatar${speakingId === m.id ? " speaking" : ""}`} aria-hidden>C</span>}
                    <div className="cc-bubble" onClick={reveal?.id === m.id ? stopReveal : undefined}>
                      {m.role === "assistant" ? (
                        <CoachText text={m.content} notes={notes} onSaveCue={saveCue}
                                   spokenAt={speakingId === m.id ? spokenAt : null}
                                   reveal={reveal?.id === m.id ? reveal.count : undefined} />
                      ) : m.content}
                      {m.role === "user" && m.delivery && (
                        <div className="cc-delivery" title="Measured from your spoken answer">
                          🎙 {deliveryLabel(m.delivery)}{paceNote(m.delivery) ? ` · ${paceNote(m.delivery)}` : ""}
                        </div>
                      )}
                      {reveal?.id !== m.id && m.visual && (
                        <VisualDiagram visual={m.visual} focus={speakingId === m.id && spokenAt >= 0 ? focusIndex(m.visual, spokenWordList(m.content), spokenAt) : -1} />
                      )}
                      {reveal?.id !== m.id && m.resources && m.resources.length > 0 && (
                        <div style={{ marginTop: 6, whiteSpace: "normal" }}>
                          {m.resources.map((r) => <ResourceCard key={r.id} item={r} compact />)}
                        </div>
                      )}
                      {m.role === "assistant" && m.id === lastCoachId && active?.status === "in_progress" &&
                        reveal?.id !== m.id && !IN_CHARACTER.includes(active.session_type) && !sending && messages.length > 1 && (
                        <div className="cc-tools">
                          <div className="cc-tools-label">Explain it differently</div>
                          <div className="cc-chips">
                            {REEXPLAIN.map((r) => (
                              <button key={r.style} className="btn btn-ghost btn-sm"
                                      onClick={() => send({ text: r.message, style: r.style })}>
                                {r.label}
                              </button>
                            ))}
                            <select className="btn btn-ghost btn-sm cc-draw" value="" aria-label="Draw it as a picture"
                                    onChange={(e) => {
                                      const opt = DRAW_AS[Number(e.target.value)];
                                      if (!opt) return;
                                      send({
                                        text: opt.kind ? `Can you draw that as ${opt.label.toLowerCase()}?` : "Can you draw that as a picture?",
                                        style: "visual", visualKind: opt.kind || undefined,
                                      });
                                    }}>
                              <option value="" disabled>Draw it as…</option>
                              {DRAW_AS.map((o, i) => <option key={o.label} value={i}>{o.label}</option>)}
                            </select>
                          </div>
                        </div>
                      )}
                      {m.role === "assistant" && reveal?.id !== m.id && (canSpeak || m.id > 0) && (
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
              {active.course_id && active.recap && (() => {
                  const mods = lessonCourse?.modules ?? [];
                  const idx = mods.findIndex((m) => m.id === active.module_id);
                  const hasNext = idx >= 0 && idx + 1 < mods.length;
                  return (
                    <ModuleRecap
                      recap={active.recap} sessionId={active.id}
                      moduleLabel={idx >= 0 ? `Module ${idx + 1}: ${mods[idx].title}` : active.topic}
                      onNext={nextModule} nextLabel={hasNext ? "Back to syllabus for the next module" : "Back to syllabus"}
                    />
                  );
                })()}

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
                    {active.homework && (
                      <p className="cc-homework"><strong>Before next time:</strong> {active.homework}</p>
                    )}
                    <button className="btn btn-ghost btn-sm" style={{ marginTop: 10 }} onClick={saveFeedback}>
                      Save to study folder
                    </button>
                  </div>
                </div>
              ) : (
                <div className="cc-composer">
                  {!IN_CHARACTER.includes(active.session_type) && (speakingId !== null || capturing) && (
                    <div className="cc-interrupt" role="group" aria-label="Interrupt the coach">
                      <span className="cc-interrupt-state" role="status">
                        {capturing
                          ? <><span className="cc-rec" aria-hidden>●</span> Go ahead. I&apos;ll send it when you pause.</>
                          : armed ? <><span className="cc-rec" aria-hidden>●</span> Listening. Say &ldquo;wait&rdquo; or &ldquo;go back&rdquo;.</>
                          : "Coach is speaking."}
                      </span>
                      {capturing ? (
                        <button className="btn btn-ghost btn-sm" onClick={cancelCapture}>Cancel</button>
                      ) : (
                        <>
                          <button className="btn btn-ghost btn-sm" onClick={replayFromSentence}>↺ Back a sentence</button>
                          <button className="btn btn-primary btn-sm" onClick={waitNow}>✋ Wait, I have a question</button>
                        </>
                      )}
                    </div>
                  )}
                  {voiceReady && voiceMode && (
                    <div className="cc-voicebar" role="status">
                      <span className="cc-voicebar-state">
                        {speakingId !== null ? "Coach is asking…"
                          : listening ? <><span className="cc-rec" aria-hidden>●</span> Recording {clock(elapsed)} · {countWords(input)} words</>
                          : input.trim() ? "Paused. Keep going or send it." : "Your turn."}
                      </span>
                      {speakingId !== null && (
                        <button className="btn btn-ghost btn-sm" onClick={() => beginDictation()}>Skip and answer</button>
                      )}
                      {speakingId === null && !listening && (
                        <button className="btn btn-ghost btn-sm" onClick={() => beginDictation()}>🎤 {input.trim() ? "Keep going" : "Start answering"}</button>
                      )}
                      <button className="btn btn-primary btn-sm" onClick={finishAnswer} disabled={sending || !input.trim()}>
                        Done — send my answer
                      </button>
                    </div>
                  )}
                  {!IN_CHARACTER.includes(active.session_type) && (
                    <>
                      <button className="btn btn-ghost btn-sm" style={{ alignSelf: "flex-start", marginBottom: 8 }} aria-expanded={padOpen}
                              onClick={() => setPadOpen((o) => !o)}>
                        ✎ Draw a diagram
                      </button>
                      <button className="btn btn-ghost btn-sm" style={{ alignSelf: "flex-start", marginBottom: 8, marginLeft: 8 }} aria-expanded={workOpen}
                              onClick={() => setWorkOpen((o) => !o)}>
                        📎 Submit your work
                      </button>
                      <div className="dp-overlay" hidden={!workOpen} role="dialog" aria-modal="true" aria-label="Submit your work"
                           onKeyDown={(e) => { if (e.key === "Escape") setWorkOpen(false); }}
                           onClick={(e) => { if (e.target === e.currentTarget) setWorkOpen(false); }}>
                        <div className="dp-panel">
                          <div className="dp-panel-head"><strong>Submit your work</strong><button className="btn btn-ghost btn-sm" onClick={() => setWorkOpen(false)}>Close</button></div>
                          <WorkArea key={active.id} disabled={sending}
                            onSend={(t, imgs) => { inputRef.current = t; setWorkOpen(false); send(undefined, undefined, imgs); }} />
                        </div>
                      </div>
                      <div className="dp-overlay" hidden={!padOpen} role="dialog" aria-modal="true" aria-label="Diagram pad"
                           onKeyDown={(e) => { if (e.key === "Escape") setPadOpen(false); }}
                           onClick={(e) => { if (e.target === e.currentTarget) setPadOpen(false); }}>
                       <div className="dp-panel">
                        <div className="dp-panel-head"><strong>Diagram pad</strong><button className="btn btn-ghost btn-sm" onClick={() => setPadOpen(false)}>Close</button></div>
                        <DiagramPad key={active.id} sessionId={active.id} disabled={sending}
                          onSaveStudy={(t) => { setPadOpen(false); setSaveDraft({ title: `${active.topic}: my diagram`, content: t, source: "manual", sourceLabel: noteLabel(active), sessionId: active.id }); }}
                          onSend={(t) => { inputRef.current = t; setPadOpen(false); send(); }}
                          onUseInReply={(t) => { setInput(t); setPadOpen(false); setTimeout(() => composerEl.current?.focus(), 0); }} />
                       </div>
                      </div>
                    </>
                  )}
                  <div className="cc-composer-row">
                    <textarea
                      ref={composerEl}
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
                      <div className="cc-checks">
                        <label className="cc-check">
                          <input type="checkbox" checked={readAloud} onChange={(e) => toggleReadAloud(e.target.checked)} disabled={voiceReady && voiceMode} />
                          Read the coach&apos;s replies aloud
                        </label>
                        {canDictate && readAloud && !IN_CHARACTER.includes(active.session_type) && (
                          <label className="cc-check" title="The microphone listens only while the coach is speaking. Headphones work best.">
                            <input type="checkbox" checked={interruptOn} onChange={(e) => toggleInterrupt(e.target.checked)} />
                            Let me interrupt by voice (headphones work best)
                          </label>
                        )}
                        {voiceReady && (
                          <label className="cc-check">
                            <input type="checkbox" checked={voiceMode} onChange={(e) => toggleVoiceMode(e.target.checked)} />
                            Voice mode: answer out loud
                          </label>
                        )}
                      </div>
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
          <CoachNotebook />
        </div>
      </div>

      {saveDraft && <SaveToStudy draft={saveDraft} onClose={() => setSaveDraft(null)} />}
    </div>
  );
}


function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

// Someone who scrolls by hand while the coach is talking is reading something
// else; the highlight stops pulling the view back for a few seconds.
let pauseFollowUntil = 0;

function followWord(el: HTMLElement) {
  if (Date.now() < pauseFollowUntil) return;
  const win = el.closest(".cc-chat-window") as HTMLElement | null;
  if (!win) return;
  const w = el.getBoundingClientRect();
  const v = win.getBoundingClientRect();
  if (w.top > v.top + 48 && w.bottom < v.bottom - 64) return;   // comfortably in view
  win.scrollTo({
    top: win.scrollTop + (w.top - v.top) - v.height * 0.35,
    behavior: prefersReducedMotion() ? "auto" : "smooth",
  });
}

// The coach sometimes writes **bold** and --- rules. Show them as real
// formatting instead of raw symbols. While the reply is being read aloud
// (spokenAt = the spoken word number) the word being said is highlighted
// along with its sentence; while it is typing in (reveal = words showing)
// only that many words are drawn.
function CoachText({ text, notes, onSaveCue, spokenAt = null, reveal }: {
  text: string; notes: string; onSaveCue: (style: CueStyle, text: string) => void;
  spokenAt?: number | null; reveal?: number;
}) {
  const layout = useMemo(() => layoutCoachText(text), [text]);
  const speaking = spokenAt !== null;
  const table = useMemo(
    () => (speaking ? currentWordTable(alignSpoken(layout.words, spokenWordList(text))) : []),
    [speaking, layout, text],
  );
  const cur = speaking && spokenAt >= 0 ? (table[Math.min(spokenAt, table.length - 1)] ?? -1) : -1;
  const curSentence = cur >= 0 ? layout.sentence[cur] : -2;
  const curRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    if (cur >= 0 && curRef.current) followWord(curRef.current);
  }, [cur]);

  useEffect(() => {
    if (!speaking) return;
    const pause = () => { pauseFollowUntil = Date.now() + 4000; };
    window.addEventListener("wheel", pause, { passive: true });
    window.addEventListener("touchmove", pause, { passive: true });
    return () => { window.removeEventListener("wheel", pause); window.removeEventListener("touchmove", pause); };
  }, [speaking]);

  const typing = reveal !== undefined;
  let hidden = false;
  const body = layout.lines.map((line, i) => {
    if (hidden) return null;
    if (line.kind === "rule") {
      return <span key={i} className="cc-rule" aria-hidden />;
    }
    if (line.kind === "cue") {
      if (typing && line.start >= reveal!) { hidden = true; return null; }
      return (
        <MemoryCue key={i} style={line.style} text={line.text}
          active={cur >= line.start && cur < line.end}
          saved={notes.includes(cueNoteLine(line.style, line.text))}
          onSave={() => onSaveCue(line.style, line.text)} />
      );
    }
    const firstWord = line.parts.flatMap((p) => p.toks).find((t) => t.w >= 0)?.w;
    if (typing && firstWord !== undefined && firstWord >= reveal!) { hidden = true; return null; }
    return (
      <span key={i} className={line.quote ? "cc-quote" : undefined}>
        {line.parts.map((part, j) => {
          const toks = part.toks.map((t, k) => {
            if (typing && t.w >= reveal!) return null;
            const word = t.w >= 0;
            const idx = word ? t.w : t.p;
            const inSentence = cur >= 0 && idx >= 0 && layout.sentence[idx] === curSentence;
            const isNow = word && t.w === cur;
            if (!word && !inSentence && !typing) return t.s;
            const cls = [word ? "cc-w" : "cc-sp", inSentence ? "sent" : "", isNow ? "now" : "", typing && word ? "cc-w-in" : ""]
              .filter(Boolean).join(" ");
            return <span key={k} className={cls} ref={isNow ? curRef : undefined}>{t.s}</span>;
          });
          if (part.bold) return <strong key={j}>{toks}</strong>;
          if (part.italic) return <em key={j}>{toks}</em>;
          return <span key={j}>{toks}</span>;
        })}
        {!line.last && !line.quote && "\n"}
      </span>
    );
  });

  if (!typing) return <>{body}</>;
  // The typing copy is silent to screen readers; they get the whole reply at once.
  return (
    <>
      <span className="visually-hidden">{text}</span>
      <span aria-hidden="true">{body}</span>
    </>
  );
}
