"use client";

import { useEffect, useRef, useState } from "react";
import { ProgressScorePoint, ProgressWeek } from "@/lib/api";

// Small, dependency-free charts for the Progress page. One series each, so
// no legend: the card title names what is plotted. Marks follow the app's
// single accent colour; text stays in ink tokens. Every chart has a table
// view and a hover/focus tooltip, so nothing depends on colour or a mouse.

const INK = "var(--ink)";
const MUTED = "var(--ink-muted)";
const GRID = "var(--border)";
const MARK = "var(--accent)";

function parseServerDate(iso: string): Date {
  const hasZone = /([zZ]|[+-]\d\d:?\d\d)$/.test(iso);
  return new Date(hasZone ? iso : iso + "Z");
}
const shortDate = (d: Date) => d.toLocaleDateString(undefined, { month: "short", day: "numeric" });

// Draw at the real pixel width so text stays 11-13px on a phone instead of
// shrinking with the picture.
function useWidth(): [React.RefObject<HTMLDivElement>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(640);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const read = () => setW(Math.max(260, Math.round(el.getBoundingClientRect().width)));
    read();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

function TableToggle({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <details className="pg-table-toggle">
      <summary>{label}</summary>
      {children}
    </details>
  );
}

// ---- Practice scores over time -----------------------------------------

export function ScoreChart({ points }: { points: ProgressScorePoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [wrapRef, W] = useWidth();
  const H = 230, L = 34, R = 28, T = 16, B = 30;
  const n = points.length;
  const x = (i: number) => (n === 1 ? (L + W - R) / 2 : L + (i * (W - L - R)) / (n - 1));
  const y = (v: number) => T + ((100 - v) * (H - T - B)) / 100;
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.score).toFixed(1)}`).join(" ");
  const last = points[n - 1];
  const hp = hover !== null ? points[hover] : null;

  return (
    <div className="pg-chart">
      <div className="pg-svg-wrap" ref={wrapRef}>
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img"
             aria-label={`Practice scores over time. Latest ${last.score} out of 100 across ${n} scored sessions.`}>
          {[0, 25, 50, 75, 100].map((v) => (
            <g key={v}>
              <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke={GRID} strokeWidth={1} />
              <text x={L - 8} y={y(v) + 4} textAnchor="end" fontSize={11} fill={MUTED}>{v}</text>
            </g>
          ))}
          {n > 1 && <path d={path} fill="none" stroke={MARK} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />}
          {points.map((p, i) => (
            <g key={p.session_id}>
              <circle cx={x(i)} cy={y(p.score)} r={i === n - 1 || i === hover ? 5 : 3}
                      fill={MARK} stroke="var(--surface)" strokeWidth={2} />
              <circle cx={x(i)} cy={y(p.score)} r={14} fill="transparent" tabIndex={0}
                      aria-label={`${shortDate(parseServerDate(p.date))}: ${p.score} out of 100, ${p.target_role}`}
                      onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
                      onFocus={() => setHover(i)} onBlur={() => setHover(null)} />
            </g>
          ))}
          <text x={Math.min(x(n - 1) + 10, W - 4)} y={y(last.score) + 4} fontSize={13} fontWeight={600} fill={INK}>{last.score}</text>
          <text x={x(0)} y={H - 8} fontSize={11} fill={MUTED} textAnchor={n === 1 ? "middle" : "start"}>{shortDate(parseServerDate(points[0].date))}</text>
          {n > 1 && <text x={x(n - 1)} y={H - 8} fontSize={11} fill={MUTED} textAnchor="end">{shortDate(parseServerDate(last.date))}</text>}
        </svg>
        {hp && hover !== null && (
          <div className="pg-tip" style={{ left: `${(x(hover) / W) * 100}%`, top: `${(y(hp.score) / H) * 100}%` }} role="status">
            <strong>{hp.score}</strong> out of 100
            <span>{shortDate(parseServerDate(hp.date))} · {hp.target_role}</span>
            {hp.topic && <span>{hp.topic}</span>}
          </div>
        )}
      </div>
      {n === 1 && <p className="hint" style={{ margin: "4px 0 0" }}>Finish one more scored session and a trend line appears.</p>}
      <TableToggle label="Show as a table">
        <table className="pg-table">
          <thead><tr><th>Date</th><th>Role</th><th>Type</th><th>Topic</th><th className="num">Score</th></tr></thead>
          <tbody>
            {[...points].reverse().map((p) => (
              <tr key={p.session_id}>
                <td>{shortDate(parseServerDate(p.date))}</td><td>{p.target_role}</td>
                <td>{p.session_type}</td><td>{p.topic || "—"}</td><td className="num">{p.score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableToggle>
    </div>
  );
}

// ---- Weekly activity ----------------------------------------------------

type Metric = "applied" | "matches" | "practice";
const METRICS: { key: Metric; label: string; noun: string }[] = [
  { key: "applied", label: "Applications sent", noun: "applications sent" },
  { key: "matches", label: "Matches found", noun: "matches found" },
  { key: "practice", label: "Practice sessions", noun: "practice sessions" },
];

export function WeekChart({ weeks }: { weeks: ProgressWeek[] }) {
  const [metric, setMetric] = useState<Metric>("applied");
  const [hover, setHover] = useState<number | null>(null);
  const [wrapRef, W] = useWidth();
  const H = 210, L = 34, R = 12, T = 18, B = 30;
  const vals = weeks.map((w) => w[metric]);
  const top = Math.max(4, Math.ceil(Math.max(...vals) / 2) * 2);
  const slot = (W - L - R) / weeks.length;
  const bw = Math.min(24, slot - 14);
  const y = (v: number) => T + ((top - v) * (H - T - B)) / top;
  const noun = METRICS.find((m) => m.key === metric)!.noun;
  const weekLabel = (w: ProgressWeek) => shortDate(new Date(w.week_start + "T00:00:00"));
  const total = vals.reduce((a, b) => a + b, 0);

  return (
    <div className="pg-chart">
      <div className="pg-seg" role="group" aria-label="Weekly measure">
        {METRICS.map((m) => (
          <button key={m.key} type="button" aria-pressed={metric === m.key}
                  className={metric === m.key ? "on" : ""} onClick={() => { setMetric(m.key); setHover(null); }}>
            {m.label}
          </button>
        ))}
      </div>
      <div className="pg-svg-wrap" ref={wrapRef}>
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img"
             aria-label={`${total} ${noun} over the last ${weeks.length} weeks.`}>
          {[0, top / 2, top].map((v) => (
            <g key={v}>
              <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke={GRID} strokeWidth={1} />
              <text x={L - 8} y={y(v) + 4} textAnchor="end" fontSize={11} fill={MUTED}>{v}</text>
            </g>
          ))}
          {weeks.map((w, i) => {
            const v = w[metric];
            const cx = L + slot * i + slot / 2;
            const x0 = cx - bw / 2, y0 = y(v), base = y(0), r = Math.min(4, bw / 2, base - y0);
            return (
              <g key={w.week_start}>
                {v > 0 && (
                  <path fill={MARK}
                        d={`M${x0},${base} V${y0 + r} Q${x0},${y0} ${x0 + r},${y0} H${x0 + bw - r} Q${x0 + bw},${y0} ${x0 + bw},${y0 + r} V${base} Z`} />
                )}
                {v > 0 && <text x={cx} y={y0 - 5} textAnchor="middle" fontSize={11} fontWeight={600} fill={INK}>{v}</text>}
                {(slot >= 46 || (weeks.length - 1 - i) % 2 === 0) && (
                  <text x={cx} y={H - 10} textAnchor="middle" fontSize={11} fill={i === weeks.length - 1 ? INK : MUTED}>{weekLabel(w)}</text>
                )}
                <rect x={L + slot * i} y={T} width={slot} height={H - T - B} fill="transparent" tabIndex={0}
                      aria-label={`Week of ${weekLabel(w)}: ${v} ${noun}`}
                      onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
                      onFocus={() => setHover(i)} onBlur={() => setHover(null)} />
              </g>
            );
          })}
        </svg>
        {hover !== null && (
          <div className="pg-tip" role="status"
               style={{ left: `${((L + slot * hover + slot / 2) / W) * 100}%`, top: `${(y(weeks[hover][metric]) / H) * 100}%` }}>
            <strong>{weeks[hover][metric]}</strong> {noun}
            <span>Week of {weekLabel(weeks[hover])}</span>
          </div>
        )}
      </div>
      <TableToggle label="Show as a table">
        <table className="pg-table">
          <thead><tr><th>Week of</th><th className="num">Matches found</th><th className="num">Applications sent</th><th className="num">Practice sessions</th></tr></thead>
          <tbody>
            {[...weeks].reverse().map((w) => (
              <tr key={w.week_start}><td>{weekLabel(w)}</td><td className="num">{w.matches}</td><td className="num">{w.applied}</td><td className="num">{w.practice}</td></tr>
            ))}
          </tbody>
        </table>
      </TableToggle>
    </div>
  );
}

// ---- Job search funnel --------------------------------------------------

export function Funnel({ funnel }: { funnel: { matched: number; approved: number; applied: number; interviewing: number; offers: number } }) {
  const steps = [
    { label: "Matched", value: funnel.matched, note: "jobs Riseply found for you" },
    { label: "Approved", value: funnel.approved, note: "you chose to pursue" },
    { label: "Applied", value: funnel.applied, note: "applications sent" },
    { label: "Interviewing", value: funnel.interviewing, note: "reached an interview" },
    { label: "Offers", value: funnel.offers, note: "offers received" },
  ];
  const max = Math.max(1, funnel.matched);
  return (
    <ul className="pg-funnel" aria-label="Job search funnel">
      {steps.map((s) => (
        <li key={s.label}>
          <div className="pg-funnel-label"><strong>{s.label}</strong><span>{s.note}</span></div>
          <div className="pg-funnel-track" aria-hidden>
            <div className="pg-funnel-fill" style={{ width: `${s.value ? Math.max(2, (100 * s.value) / max) : 0}%` }} />
          </div>
          <div className="pg-funnel-value">{s.value}</div>
        </li>
      ))}
    </ul>
  );
}
