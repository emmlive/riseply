"use client";

import { clockText, minutesText } from "@/lib/sessionClock";

const CHOICES = [0, 15, 30, 45, 60, 90];

// The timer in a session's header: time spent so far and, when a limit is set,
// how much is left. It never cuts the person off; at the limit it says so and
// offers more time, and the coach is told to wrap up.
export default function SessionClock({ seconds, limitMin, onLimit, live }: {
  seconds: number; limitMin: number; onLimit: (m: number) => void; live: boolean;
}) {
  const left = limitMin > 0 ? limitMin * 60 - seconds : null;
  const state = left === null ? "" : left <= 0 ? "is-over" : left <= 300 ? "is-low" : "";
  if (!live) {
    return <div className="sc-bar"><span>Time spent: <strong>{minutesText(seconds)}</strong>{limitMin ? ` of ${limitMin} min planned` : ""}</span></div>;
  }
  return (
    <div className={`sc-bar ${state}`} role="timer" aria-label="Session timer">
      <span className="sc-time" aria-live="off">
        ⏱ <strong>{clockText(left === null ? seconds : Math.abs(left))}</strong>{" "}
        {left === null ? "spent" : left <= 0 ? "over your time" : "left"}
      </span>
      <span className="sc-ctl">
        <label>
          <span className="sc-sr">Time limit</span>
          <select className="cc-input sc-select" value={CHOICES.includes(limitMin) ? limitMin : -1} onChange={(e) => onLimit(Number(e.target.value))} aria-label="Time limit">
            {CHOICES.map((m) => <option key={m} value={m}>{m === 0 ? "No limit" : `${m} min`}</option>)}
            {!CHOICES.includes(limitMin) && <option value={-1} disabled>{limitMin} min</option>}
          </select>
        </label>
        {left !== null && left <= 300 && (
          <button className="btn btn-ghost btn-sm" onClick={() => onLimit(limitMin + 10)}>+10 min</button>
        )}
      </span>
      {left !== null && left <= 0 && (
        <p className="sc-note" role="status">Your time is up. Wrap up with &ldquo;End session and get feedback&rdquo;, or add 10 minutes to keep going.</p>
      )}
    </div>
  );
}
