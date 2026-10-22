"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, CareerCoachSession } from "@/lib/api";

// The session clock: counts the time the person actually spends working in a
// session. It only runs while the tab is visible and there has been some
// activity (typing, clicking, scrolling, or the coach answering) in the last
// five minutes, so leaving the page open overnight costs nothing. Time is
// saved to the server every 30 seconds so it survives a reload or another device.
const IDLE_MS = 5 * 60 * 1000;
const SAVE_EVERY_S = 30;

export type TimerState = "running" | "paused" | "stopped";

export function useSessionClock(active: CareerCoachSession | null, busy: boolean) {
  const [seconds, setSeconds] = useState(0);
  const [limitMin, setLimitMin] = useState(0);
  const [state, setStateRaw] = useState<TimerState>("running");
  const stateRef = useRef<TimerState>("running");
  const secRef = useRef(0);
  const savedRef = useRef(0);
  const lastActive = useRef(Date.now());
  const busyRef = useRef(busy);
  busyRef.current = busy;
  const id = active?.id ?? null;
  const live = !!active && active.status === "in_progress";

  const save = useCallback((sid: number | null, extra?: { time_limit_min?: number; timer_state?: TimerState }) => {
    if (sid === null) return;
    if (secRef.current === savedRef.current && !extra) return;
    const body = { active_seconds: secRef.current, ...(extra ?? {}) };
    savedRef.current = secRef.current;
    api(`/career-coach/sessions/${sid}/clock`, { method: "PUT", body: JSON.stringify(body) }).catch(() => {});
  }, []);

  // New session: start from what the server has.
  useEffect(() => {
    const s = active?.active_seconds ?? 0;
    secRef.current = s; savedRef.current = s;
    setSeconds(s);
    setLimitMin(active?.time_limit_min ?? 0);
    const st = (active?.timer_state || "running") as TimerState;
    stateRef.current = st; setStateRaw(st);
    lastActive.current = Date.now();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (!live) return;
    const touch = () => { lastActive.current = Date.now(); };
    const evs = ["pointerdown", "keydown", "scroll", "pointermove"] as const;
    evs.forEach((e) => window.addEventListener(e, touch, { passive: true }));
    const tick = setInterval(() => {
      if (busyRef.current) lastActive.current = Date.now();
      if (stateRef.current !== "running" || document.visibilityState !== "visible" || Date.now() - lastActive.current > IDLE_MS) return;
      secRef.current += 1;
      setSeconds(secRef.current);
      if (secRef.current % SAVE_EVERY_S === 0) save(id);
    }, 1000);
    const flush = () => save(id);
    document.addEventListener("visibilitychange", flush);
    window.addEventListener("pagehide", flush);
    return () => {
      clearInterval(tick);
      evs.forEach((e) => window.removeEventListener(e, touch));
      document.removeEventListener("visibilitychange", flush);
      window.removeEventListener("pagehide", flush);
      save(id);
    };
  }, [id, live, save]);

  const setLimit = useCallback((min: number) => {
    setLimitMin(min);
    save(id, { time_limit_min: min });
  }, [id, save]);

  // Pause holds the time and the limit; stop ends the timing (and the coach's pacing) until restarted.
  const setState = useCallback((st: TimerState) => {
    stateRef.current = st; setStateRaw(st);
    save(id, { timer_state: st });
  }, [id, save]);

  const minutesLeft = limitMin > 0 && state !== "stopped" ? Math.ceil((limitMin * 60 - seconds) / 60) : null;
  return { seconds, limitMin, setLimit, state, setState, minutesLeft, flush: () => save(id) };
}

export function clockText(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const mm = String(m).padStart(2, "0"), ss = String(sec).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
}

export function minutesText(totalSeconds: number): string {
  const m = Math.round(totalSeconds / 60);
  return m < 1 ? "under a minute" : m === 1 ? "1 minute" : `${m} minutes`;
}
