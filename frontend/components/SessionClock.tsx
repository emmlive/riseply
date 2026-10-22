"use client";

import { TimerState, clockText, minutesText } from "@/lib/sessionClock";

const CHOICES = [0, 15, 30, 45, 60, 90];

// The timer in a session's header: time spent so far and, when a limit is set,
// how much is left. It can be paused (holds the time and the limit) or stopped
// (ends the timing, keeps the time spent). It never cuts the person off; at
// the limit it says so and offers more time, and the coach is told to wrap up.
export default function SessionClock({ seconds, limitMin, onLimit, state, onState, live }: {
  seconds: number; limitMin: number; onLimit: (m: number) => void;
  state: TimerState; onState: (s: TimerState) => void; live: boolean;
}) {
  if (!live) {
    return <div className="sc-bar"><span>Time spent: <strong>{minutesText(seconds)}</strong>{limitMin ? ` of ${limitMin} min planned` : ""}</span></div>;
  }
  if (state === "stopped") {
    return (
      <div className="sc-bar" role="timer" aria-label="Session timer">
        <span className="sc-time">⏹ Timer stopped · <strong>{clockText(seconds)}</strong> spent</span>
        <button className="btn btn-ghost btn-sm" onClick={() => onState("running")}>Restart timer</button>
      </div>
    );
  }
  const left = limitMin > 0 ? limitMin * 60 - seconds : null;
  const paused = state === "paused";
  const tone = paused ? "is-paused" : left === null ? "" : left <= 0 ? "is-over" : left <= 300 ? "is-low" : "";
  return (
    <div className={`sc-bar ${tone}`} role="timer" aria-label="Session timer">
      <span className="sc-time" aria-live="off">
        {paused ? "⏸ Paused · " : "⏱ "}<strong>{clockText(left === null ? seconds : Math.abs(left))}</strong>{" "}
        {left === null ? "spent" : left <= 0 ? "over your time" : "left"}
      </span>
      <span className="sc-ctl">
        <button className="btn btn-ghost btn-sm" onClick={() => onState(paused ? "running" : "paused")} aria-pressed={paused}>
          {paused ? "Resume" : "Pause"}
        </button>
        <button className="btn btn-ghost btn-sm" onClick={() => onState("stopped")} title="Stop timing this session. The time spent so far is kept.">Stop</button>
        <label>
          <span className="sc-sr">Time limit</span>
          <select className="cc-input sc-select" value={CHOICES.includes(limitMin) ? limitMin : -1} onChange={(e) => onLimit(Number(e.target.value))} aria-label="Time limit">
            {CHOICES.map((m) => <option key={m} value={m}>{m === 0 ? "No limit" : `${m} min`}</option>)}
            {!CHOICES.includes(limitMin) && <option value={-1} disabled>{limitMin} min</option>}
          </select>
        </label>
        {left !== null && left <= 300 && !paused && (
          <button className="btn btn-ghost btn-sm" onClick={() => onLimit(limitMin + 10)}>+10 min</button>
        )}
      </span>
      {left !== null && left <= 0 && !paused && (
        <p className="sc-note" role="status">Your time is up. Wrap up with &ldquo;End session and get feedback&rdquo;, or add 10 minutes to keep going.</p>
      )}
    </div>
  );
}
