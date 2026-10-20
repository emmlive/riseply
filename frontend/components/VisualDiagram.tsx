"use client";

import { useState } from "react";
import { CareerCoachVisual } from "@/lib/api";

// Draws a diagram the Career Coach produced while teaching. The coach
// supplies structured data only; everything here is plain React text
// nodes (so any markup in a label is shown inertly, never executed) and
// theme-variable CSS. Seven shapes: flow (ordered steps), cycle (steps that
// loop back), compare (table), map (center idea with branches), matrix (a
// 2x2 grid), layers (a stack or pyramid) and chart (bars of numbers). Items
// may carry one emoji icon, which is decoration only.

// On the whiteboard (.wb in globals.css) these variables turn the boxes into
// hand-drawn marker outlines; elsewhere they fall back to the plain look.
const box: React.CSSProperties = {
  border: "var(--wb-border, 1px solid var(--border))", borderRadius: "var(--wb-radius, 8px)",
  padding: "6px 10px", background: "var(--paper)",
};

// Each piece of the drawing appears in turn, like a teacher writing it out.
const step = (i: number): React.CSSProperties => ({ ["--i" as string]: i } as React.CSSProperties);

const Icon = ({ icon }: { icon?: string }) =>
  icon ? <span aria-hidden style={{ fontSize: "1.15em", lineHeight: 1, marginRight: 6 }}>{icon}</span> : null;

function formatNumber(n: number): string {
  try { return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(n); } catch { return String(n); }
}

export default function VisualDiagram({ visual }: { visual: CareerCoachVisual }) {
  const title = visual.title || "Diagram";
  const [run, setRun] = useState(0);   // bumping this redraws the board from the start
  return (
    <figure aria-label={title} className="wb">
      <div className="wb-top">
        <figcaption className="wb-title">{visual.title || "On the board"}</figcaption>
        <button type="button" className="wb-replay" onClick={() => setRun((n) => n + 1)} aria-label="Draw it again">↻ Draw again</button>
      </div>
      <div key={run} className="wb-board">

      {(visual.kind === "flow" || visual.kind === "cycle") && (
        <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", alignItems: "stretch" }}>
          {visual.steps.map((s, i) => (
            <li key={i} className="wb-draw" style={{ display: "flex", flexDirection: "column", alignItems: "stretch", ...step(i) }}>
              <div style={{ ...box, display: "flex", gap: 10, alignItems: "baseline" }}>
                <span className="ticket" style={{ minWidth: 24, textAlign: "center" }}>{i + 1}</span>
                <span>
                  <Icon icon={s.icon} /><strong>{s.label}</strong>
                  {s.detail && <span className="hint" style={{ display: "block" }}>{s.detail}</span>}
                </span>
              </div>
              {i < visual.steps.length - 1 && (
                <div aria-hidden style={{ textAlign: "center", lineHeight: 1.1, color: "var(--muted, #888)" }}>↓</div>
              )}
            </li>
          ))}
          {visual.kind === "cycle" && (
            <li className="wb-draw" style={{ display: "flex", flexDirection: "column", alignItems: "stretch", ...step(visual.steps.length) }}>
              <div aria-hidden style={{ textAlign: "center", lineHeight: 1.1, color: "var(--muted, #888)" }}>↓</div>
              <div style={{
                ...box, textAlign: "center", borderStyle: "dashed", borderColor: "var(--accent)",
                background: "var(--accent-soft)", fontWeight: 600,
              }}>
                <span aria-hidden>↺ </span>Back to step 1: {visual.steps[0]?.label}
              </div>
            </li>
          )}
        </ol>
      )}

      {visual.kind === "layers" && (
        <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
          {visual.steps.map((s, i) => {
            const n = visual.steps.length;
            const width = n > 1 ? 44 + (56 * i) / (n - 1) : 100;   // narrow at the top, wide at the base
            const tint = Math.round(10 + (90 * i) / Math.max(1, n - 1));
            return (
              <li key={i} className="wb-draw" style={{
                ...step(i), ...box, width: `${width}%`, textAlign: "center",
                background: `color-mix(in srgb, var(--accent) ${tint}%, var(--surface))`,
                color: tint > 75 ? "#fff" : "var(--ink)", borderColor: "var(--accent)",
              }}>
                <Icon icon={s.icon} /><strong>{s.label}</strong>
                {s.detail && <span style={{ display: "block", fontSize: 13, opacity: 0.9 }}>{s.detail}</span>}
              </li>
            );
          })}
        </ol>
      )}

      {visual.kind === "matrix" && visual.quadrants && visual.axes && (
        <div style={{ display: "grid", gridTemplateColumns: "auto minmax(0, 1fr)", gridTemplateRows: "minmax(0, 1fr) auto", gap: 6 }}>
          <div aria-hidden style={{
            writingMode: "vertical-rl", transform: "rotate(180deg)", textAlign: "center", fontWeight: 600,
            fontSize: 13, color: "var(--ink-muted)",
          }}>{visual.axes[1]} →</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 6 }}>
            {visual.quadrants.map((q, i) => (
              <div key={i} className="wb-draw" style={{ ...step(i), ...box, background: i === 0 ? "var(--accent-soft)" : "var(--paper)", minHeight: 84, minWidth: 0, overflowWrap: "break-word", fontSize: 13.5, padding: "6px 8px" }}>
                <div style={{ fontWeight: 600 }}><Icon icon={q.icon} />{q.label}</div>
                {q.items.length > 0 && (
                  <ul style={{ margin: "4px 0 0", padding: 0, listStyle: "none" }}>
                    {q.items.map((it, j) => <li key={j} style={{ marginTop: 2 }}><span aria-hidden>• </span>{it}</li>)}
                  </ul>
                )}
              </div>
            ))}
          </div>
          <span />
          <div aria-hidden style={{ textAlign: "center", fontWeight: 600, fontSize: 13, color: "var(--ink-muted)" }}>{visual.axes[0]} →</div>
          <span className="visually-hidden">Horizontal axis: {visual.axes[0]}. Vertical axis: {visual.axes[1]}. Quadrants run top-left, top-right, bottom-left, bottom-right.</span>
        </div>
      )}

      {visual.kind === "chart" && visual.bars && (() => {
        const max = Math.max(...visual.bars.map((b) => b.value), 1);
        return (
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
            {visual.bars.map((b, i) => (
              <li key={i} className="wb-draw" style={step(i)}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10, fontSize: 14 }}>
                  <span><Icon icon={b.icon} />{b.label}</span>
                  <strong>{formatNumber(b.value)}{visual.unit ? ` ${visual.unit}` : ""}</strong>
                </div>
                <div aria-hidden style={{ height: 10, borderRadius: 999, background: "var(--wb-track, var(--border))", overflow: "hidden", marginTop: 3 }}>
                  <div style={{ width: `${Math.max(2, (b.value / max) * 100)}%`, height: "100%", background: "var(--accent)", borderRadius: 999 }} />
                </div>
              </li>
            ))}
          </ul>
        );
      })()}

      {visual.kind === "compare" && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 14 }}>
            <thead>
              <tr>
                <th style={{ ...box, textAlign: "left" }} />
                {visual.columns.map((c, i) => <th key={i} style={{ ...box, textAlign: "left" }}>{c}</th>)}
              </tr>
            </thead>
            <tbody>
              {visual.rows.map((r, i) => (
                <tr key={i} className="wb-fade" style={step(i)}>
                  <th scope="row" style={{ ...box, textAlign: "left" }}>{r.label}</th>
                  {visual.columns.map((_, j) => <td key={j} style={box}>{r.cells[j] ?? ""}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {visual.kind === "map" && (
        <div>
          <div className="wb-draw" style={{ ...step(0), ...box, textAlign: "center", fontWeight: 700, marginBottom: 8, borderColor: "var(--accent)", background: "var(--accent-soft)" }}>
            {visual.center}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8 }}>
            {visual.branches.map((b, i) => (
              <div key={i} className="wb-draw" style={{ ...step(i + 1), ...box }}>
                <div style={{ fontWeight: 600 }}><Icon icon={b.icon} />{b.label}</div>
                <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                  {b.items.map((it, j) => <li key={j}>{it}</li>)}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}
      </div>
      <div className="wb-tray" aria-hidden><i /><i /><i /><i /></div>
    </figure>
  );
}
