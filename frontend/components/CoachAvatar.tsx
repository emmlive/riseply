"use client";

import { useEffect, useRef, useState } from "react";
import "./CoachAvatar.css";

// The coach's presence in the corner of the screen: a calm card with a live
// voice waveform. The bars move with the coach's speech (each spoken word
// gives the wave a push), slow down while the coach listens to you, and rest
// while the coach thinks or waits.

type Mood = "speaking" | "listening" | "thinking" | "idle";

const BARS = 25;
const FLAT = 0.08;

export default function CoachAvatar({
  mood, word, voiceOn, canSpeak, onToggleVoice, onHide,
}: {
  mood: Mood;
  word: string | null;
  voiceOn: boolean;
  canSpeak: boolean;
  onToggleVoice: () => void;
  onHide: () => void;
}) {
  const [levels, setLevels] = useState<number[]>(() => Array(BARS).fill(FLAT));
  const [dot, setDot] = useState(0);
  const wordRef = useRef<string | null>(null);
  wordRef.current = word;

  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setLevels(Array(BARS).fill(mood === "speaking" ? 0.35 : FLAT));
      return;
    }
    if (mood === "idle") { setLevels(Array(BARS).fill(FLAT)); return; }
    if (mood === "thinking") {
      setLevels(Array(BARS).fill(FLAT));
      const id = window.setInterval(() => setDot((d) => (d + 1) % 3), 420);
      return () => window.clearInterval(id);
    }
    let push = 0.6;
    let last: string | null = null;
    const id = window.setInterval(() => {
      const w = wordRef.current;
      if (mood === "speaking" && w !== last) { last = w; push = Math.min(1, 0.55 + (w ? w.length : 3) * 0.06); }
      push *= 0.86;
      setLevels((prev) => {
        const next = prev.slice(1);
        const centre = 1 - Math.abs(next.length / 2 - BARS / 2) / BARS;   // taller in the middle
        const base = mood === "speaking" ? 0.18 + push * 0.7 : 0.1 + Math.random() * 0.12;
        next.push(Math.max(FLAT, Math.min(1, (base + Math.random() * 0.25) * (0.55 + centre * 0.6))));
        return next;
      });
    }, mood === "speaking" ? 70 : 140);
    return () => window.clearInterval(id);
  }, [mood]);

  const label =
    mood === "speaking" ? "Speaking"
    : mood === "listening" ? "Listening to you"
    : mood === "thinking" ? "Thinking"
    : "Ready";

  return (
    <aside className={`ca ca-${mood}`} aria-label="Career coach">
      <div className="ca-card">
        <div className="ca-top">
          <span className="ca-mark" aria-hidden>C</span>
          <span className="ca-who">
            <strong>Your Career Coach</strong>
            <span className="ca-state" role="status"><i className="ca-dot" aria-hidden />{label}</span>
          </span>
        </div>
        <div className="ca-wave" aria-hidden>
          {mood === "thinking" ? (
            <span className="ca-dots">{[0, 1, 2].map((i) => <i key={i} className={dot === i ? "on" : ""} />)}</span>
          ) : (
            levels.map((v, i) => <span key={i} style={{ height: `${Math.round(v * 100)}%` }} />)
          )}
        </div>
        <div className="ca-actions">
          {canSpeak && (
            <button type="button" className="ca-btn" onClick={onToggleVoice} aria-pressed={voiceOn}
              title={voiceOn ? "Mute the coach" : "Let the coach talk"}>
              {voiceOn ? "Mute voice" : "Turn on voice"}
            </button>
          )}
          <button type="button" className="ca-btn" onClick={onHide} title="Hide the coach">Hide</button>
        </div>
      </div>
    </aside>
  );
}
