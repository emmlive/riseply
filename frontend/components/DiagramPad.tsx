"use client";

import { useRef, useState } from "react";
import { BOX_H, BOX_W, CANVAS_H, CANVAS_W, DItem, DLink, MAX_ITEMS, describeDiagram, edgePoint } from "@/lib/diagram";

// A drawing area inside a coach session. Add zones and boxes, drag them,
// connect them with arrows, label everything, then send it to the coach as
// text. Works with a mouse, touch or the keyboard (arrow keys move the
// selected shape).
let uid = 0;
const nid = (p: string) => `${p}${++uid}`;
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

export default function DiagramPad({ onSend, onUseInReply, disabled }: {
  onSend: (text: string) => void;
  onUseInReply: (text: string) => void;
  disabled?: boolean;
}) {
  const [items, setItems] = useState<DItem[]>([]);
  const [links, setLinks] = useState<DLink[]>([]);
  const [sel, setSel] = useState<{ type: "item" | "link"; id: string } | null>(null);
  const [connecting, setConnecting] = useState<string | null | false>(false); // false = off, null = pick source, id = pick target
  const [note, setNote] = useState("");
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<{ id: string; mode: "move" | "size"; dx: number; dy: number } | null>(null);
  const labelEl = useRef<HTMLInputElement>(null);

  const selItem = sel?.type === "item" ? items.find((i) => i.id === sel.id) : undefined;
  const selLink = sel?.type === "link" ? links.find((l) => l.id === sel.id) : undefined;

  function point(e: React.PointerEvent) {
    const m = svg.current!.getScreenCTM()!.inverse();
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m);
    return { x: p.x, y: p.y };
  }

  function add(kind: "zone" | "box") {
    if (items.length >= MAX_ITEMS) return;
    const n = items.filter((i) => i.kind === kind).length;
    const w = kind === "zone" ? 300 : BOX_W, h = kind === "zone" ? 300 : BOX_H;
    const it: DItem = {
      id: nid(kind[0]), kind, w, h, label: "",
      x: clamp(kind === "zone" ? 20 + n * 340 : 60 + (n % 4) * 30, 0, CANVAS_W - w),
      y: clamp(kind === "zone" ? 50 : 100 + (n % 5) * 56, 0, CANVAS_H - h),
    };
    if (kind === "zone") { it.h = 330; }
    setItems((s) => (kind === "zone" ? [it, ...s] : [...s, it]));   // zones sit behind boxes
    setSel({ type: "item", id: it.id });
    setConnecting(false);
    setTimeout(() => labelEl.current?.focus(), 0);
  }

  function onDown(e: React.PointerEvent, it: DItem, mode: "move" | "size") {
    e.stopPropagation();
    if (connecting !== false && it.kind === "box" && mode === "move") {
      if (connecting === null) { setConnecting(it.id); setSel({ type: "item", id: it.id }); }
      else if (connecting !== it.id) {
        const id = nid("l");
        setLinks((s) => [...s, { id, from: connecting, to: it.id, label: "" }]);
        setSel({ type: "link", id });
        setConnecting(false);
      }
      return;
    }
    (e.target as Element).setPointerCapture(e.pointerId);
    const p = point(e);
    drag.current = { id: it.id, mode, dx: p.x - (mode === "move" ? it.x : it.x + it.w), dy: p.y - (mode === "move" ? it.y : it.y + it.h) };
    setSel({ type: "item", id: it.id });
  }

  function onMove(e: React.PointerEvent) {
    const d = drag.current;
    if (!d) return;
    const p = point(e);
    setItems((s) => s.map((i) => {
      if (i.id !== d.id) return i;
      if (d.mode === "move") return { ...i, x: clamp(p.x - d.dx, 0, CANVAS_W - i.w), y: clamp(p.y - d.dy, 0, CANVAS_H - i.h) };
      return { ...i, w: clamp(p.x - d.dx - i.x, 90, CANVAS_W - i.x), h: clamp(p.y - d.dy - i.y, 70, CANVAS_H - i.y) };
    }));
  }

  function onKey(e: React.KeyboardEvent, it: DItem) {
    const step = e.shiftKey ? 30 : 10;
    const mv: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (mv[e.key]) {
      e.preventDefault();
      const [dx, dy] = mv[e.key];
      setItems((s) => s.map((i) => (i.id === it.id ? { ...i, x: clamp(i.x + dx, 0, CANVAS_W - i.w), y: clamp(i.y + dy, 0, CANVAS_H - i.h) } : i)));
    } else if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); remove(); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSel({ type: "item", id: it.id }); labelEl.current?.focus(); }
  }

  function remove() {
    if (!sel) return;
    if (sel.type === "link") setLinks((s) => s.filter((l) => l.id !== sel.id));
    else { setItems((s) => s.filter((i) => i.id !== sel.id)); setLinks((s) => s.filter((l) => l.from !== sel.id && l.to !== sel.id)); }
    setSel(null);
  }

  function setLabel(v: string) {
    if (selItem) setItems((s) => s.map((i) => (i.id === selItem.id ? { ...i, label: v.slice(0, 60) } : i)));
    else if (selLink) setLinks((s) => s.map((l) => (l.id === selLink.id ? { ...l, label: v.slice(0, 60) } : l)));
  }

  const text = describeDiagram(items, links, note);
  const boxCount = items.filter((i) => i.kind === "box").length;
  const byId = new Map(items.map((i) => [i.id, i] as const));

  return (
    <div className="dp">
      <div className="dp-bar" role="toolbar" aria-label="Diagram tools">
        <button className="btn btn-ghost btn-sm" onClick={() => add("zone")}>+ Zone</button>
        <button className="btn btn-ghost btn-sm" onClick={() => add("box")}>+ Box</button>
        <button className={`btn btn-sm ${connecting === false ? "btn-ghost" : "btn-primary"}`} aria-pressed={connecting !== false}
                onClick={() => setConnecting(connecting === false ? null : false)} disabled={boxCount < 2}>
          {connecting === false ? "Connect two boxes" : connecting === null ? "Pick the first box…" : "Now pick the second box…"}
        </button>
        <button className="btn btn-ghost btn-sm" onClick={remove} disabled={!sel}>Delete selected</button>
        <button className="btn btn-ghost btn-sm" onClick={() => { setItems([]); setLinks([]); setSel(null); setNote(""); }} disabled={!items.length}>Clear</button>
      </div>

      <svg ref={svg} className="dp-canvas" viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`} role="group"
           aria-label="Drawing area. Select a shape and use the arrow keys to move it."
           onPointerMove={onMove} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}
           onPointerDown={() => { if (connecting === false) setSel(null); }}>
        <defs>
          <marker id="dp-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" fill="currentColor" />
          </marker>
        </defs>
        {items.length === 0 && (
          <text x={CANVAS_W / 2} y={CANVAS_H / 2} textAnchor="middle" className="dp-empty">Add a zone or a box to start drawing</text>
        )}
        {items.filter((i) => i.kind === "zone").map((z) => (
          <g key={z.id} className={`dp-zone ${sel?.id === z.id ? "is-sel" : ""}`}>
            <rect x={z.x} y={z.y} width={z.w} height={z.h} rx={10} tabIndex={0} role="button"
                  aria-label={`Zone ${z.label || "unnamed"}`} onPointerDown={(e) => onDown(e, z, "move")} onKeyDown={(e) => onKey(e, z)} />
            <text x={z.x + 12} y={z.y + 20} className="dp-zone-label">{z.label || "Unnamed zone"}</text>
            <rect x={z.x + z.w - 14} y={z.y + z.h - 14} width={14} height={14} className="dp-grip" aria-hidden
                  onPointerDown={(e) => onDown(e, z, "size")} />
          </g>
        ))}
        {links.map((l) => {
          const a = byId.get(l.from), b = byId.get(l.to);
          if (!a || !b) return null;
          const p = edgePoint(a, b), q = edgePoint(b, a);
          return (
            <g key={l.id} className={`dp-link ${sel?.id === l.id ? "is-sel" : ""}`}>
              <line x1={p.x} y1={p.y} x2={q.x} y2={q.y} markerEnd="url(#dp-arrow)" />
              <line x1={p.x} y1={p.y} x2={q.x} y2={q.y} className="dp-hit" onPointerDown={(e) => { e.stopPropagation(); setSel({ type: "link", id: l.id }); }} />
              {l.label && <text x={(p.x + q.x) / 2} y={(p.y + q.y) / 2 - 6} textAnchor="middle">{l.label}</text>}
            </g>
          );
        })}
        {items.filter((i) => i.kind === "box").map((b) => (
          <g key={b.id} className={`dp-box ${sel?.id === b.id ? "is-sel" : ""} ${connecting === b.id ? "is-source" : ""}`}>
            <rect x={b.x} y={b.y} width={b.w} height={b.h} rx={8} tabIndex={0} role="button"
                  aria-label={`Box ${b.label || "unnamed"}`} onPointerDown={(e) => onDown(e, b, "move")} onKeyDown={(e) => onKey(e, b)} />
            <text x={b.x + b.w / 2} y={b.y + b.h / 2 + 5} textAnchor="middle" pointerEvents="none">{(b.label || "Unnamed box").slice(0, 18)}</text>
          </g>
        ))}
      </svg>

      <div className="dp-edit">
        {(selItem || selLink) ? (
          <label className="dp-field">
            <span>{selItem ? (selItem.kind === "zone" ? "Zone name" : "Box name") : "What travels along this arrow (optional)"}</span>
            <input ref={labelEl} className="cc-input" value={selItem ? selItem.label : selLink!.label} maxLength={60}
                   onChange={(e) => setLabel(e.target.value)}
                   placeholder={selItem?.kind === "zone" ? "For example: Internet" : selItem ? "For example: Web server" : "For example: HTTPS requests"} />
          </label>
        ) : <p className="muted dp-hint">Click a shape to name it. Drag to move. Drag the corner of a zone to resize it.</p>}
      </div>

      <label className="dp-field">
        <span>Your explanation (optional, goes with the diagram)</span>
        <textarea className="cc-input" rows={3} value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)}
                  placeholder="For example: one sentence on why each zone exists, and what the boundary protects against." />
      </label>
      <div className="dp-actions">
        <button className="btn btn-primary btn-sm" disabled={!items.length || disabled} onClick={() => onSend(text)}>Send diagram to the coach</button>
        <button className="btn btn-ghost btn-sm" disabled={!items.length} onClick={() => onUseInReply(text)}>Put it in my reply box</button>
      </div>
    </div>
  );
}
