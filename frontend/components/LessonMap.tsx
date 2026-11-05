"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, LessonMapData } from "@/lib/api";
import "./LessonMap.css";

const AUTO_KEY = "cc-map-auto";
const HUES = ["#1F7A6C", "#3B73C4", "#C97A2B", "#8B5FBF", "#C24444", "#4F8A3A"];

// The map as plain text, for saving to a study folder.
export function mapOutline(m: LessonMapData): string {
  const out: string[] = [m.title || "Lesson map", ""];
  for (const b of m.branches) {
    out.push(b.label, ...b.items.map((i) => `- ${i}`), "");
  }
  return out.join("\n").trim();
}

function Tree({ map, layout, fresh, disabled, onAsk }: {
  map: LessonMapData; layout: "v" | "h"; fresh: Set<string>; disabled: boolean; onAsk: (text: string) => void;
}) {
  return (
    <div className={`lm-tree lm-${layout}`}>
      <div className="lm-center">{map.title || "Lesson"}</div>
      <ul className="lm-branches">
        {map.branches.map((b, bi) => (
          <li key={b.label} className="lm-branch" style={{ ["--hue" as any]: HUES[bi % HUES.length] }}>
            <button type="button" className={`lm-label${fresh.has(`b:${b.label}`) ? " lm-new" : ""}`} disabled={disabled}
                    title="Ask the coach to go deeper on this"
                    onClick={() => onAsk(`Go deeper on "${b.label}". Explain it practically, with an example.`)}>
              {b.icon ? <span aria-hidden>{b.icon} </span> : null}{b.label}
            </button>
            {b.items.length > 0 && (
              <ul className="lm-items">
                {b.items.map((it) => (
                  <li key={it} className="lm-item">
                    <button type="button" className={`lm-pt${fresh.has(`i:${b.label}|${it}`) ? " lm-new" : ""}`} disabled={disabled}
                            title="Ask the coach to explain this"
                            onClick={() => onAsk(`Explain "${it}" (part of ${b.label}) in a practical way.`)}>
                      {it}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

// The lesson mind map for one learning session. It grows as the coach teaches:
// each new reply adds only what it taught. Tap a branch or point to ask the
// coach to go deeper; expand it to study; save it to a study folder.
export default function LessonMap({ sessionId, freshReplyId, busy, onAsk, onSave }: {
  sessionId: number;
  freshReplyId: number | null;     // a coach reply that just arrived, to add to the map
  busy: boolean;                    // the coach is answering: hold questions
  onAsk: (text: string) => void;
  onSave: (outline: string, title: string) => void;
}) {
  const [map, setMap] = useState<LessonMapData | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [auto, setAuto] = useState(true);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState(false);
  const mapRef = useRef<LessonMapData | null>(null);
  mapRef.current = map;
  const handled = useRef<number | null>(null);
  const freshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => { try { setAuto(localStorage.getItem(AUTO_KEY) !== "0"); } catch { /* ignore */ } }, []);

  const load = useCallback(() => {
    setMap(null); setError(""); setFresh(new Set());
    api<LessonMapData>(`/career-coach/sessions/${sessionId}/map`).then(setMap).catch(() => setMap({ title: "", branches: [] }));
  }, [sessionId]);
  useEffect(() => { load(); handled.current = null; }, [load]);
  useEffect(() => () => { if (freshTimer.current) clearTimeout(freshTimer.current); }, []);

  function markNew(before: LessonMapData | null, after: LessonMapData) {
    const old = new Set<string>();
    for (const b of before?.branches ?? []) { old.add(`b:${b.label}`); b.items.forEach((i) => old.add(`i:${b.label}|${i}`)); }
    const next = new Set<string>();
    for (const b of after.branches) {
      if (!old.has(`b:${b.label}`)) next.add(`b:${b.label}`);
      b.items.forEach((i) => { if (!old.has(`i:${b.label}|${i}`)) next.add(`i:${b.label}|${i}`); });
    }
    setFresh(next);
    if (freshTimer.current) clearTimeout(freshTimer.current);
    freshTimer.current = setTimeout(() => setFresh(new Set()), 6000);
  }

  const update = useCallback(async (messageId: number | null) => {
    setWorking(true); setError("");
    try {
      const r = await api<{ map: LessonMapData; added: number }>(`/career-coach/sessions/${sessionId}/map`, {
        method: "POST", body: JSON.stringify(messageId === null ? {} : { message_id: messageId }),
      });
      markNew(mapRef.current, r.map);
      setMap(r.map);
    } catch (e: any) {
      setError(e?.message || "Couldn't update the map just now.");
    } finally {
      setWorking(false);
    }
  }, [sessionId]);

  // A new coach reply: add what it taught (when "add as we go" is on).
  useEffect(() => {
    if (freshReplyId === null || freshReplyId <= 0 || handled.current === freshReplyId || !auto || map === null) return;
    handled.current = freshReplyId;
    update(freshReplyId);
  }, [freshReplyId, auto, map, update]);

  function toggleAuto(on: boolean) {
    setAuto(on);
    try { localStorage.setItem(AUTO_KEY, on ? "1" : "0"); } catch { /* ignore */ }
  }

  async function clear() {
    if (!map?.branches.length || !window.confirm("Clear this map? You can rebuild it from the lesson any time.")) return;
    try { setMap(await api<LessonMapData>(`/career-coach/sessions/${sessionId}/map`, { method: "DELETE" })); setFresh(new Set()); }
    catch (e: any) { setError(e?.message || "Couldn't clear the map."); }
  }

  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setExpanded(false); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [expanded]);

  const empty = !!map && map.branches.length === 0;
  const ask = (text: string) => { setExpanded(false); onAsk(text); };

  return (
    <div className="lm">
      <label className="cc-check lm-auto">
        <input type="checkbox" checked={auto} onChange={(e) => toggleAuto(e.target.checked)} />
        Add to the map as the coach teaches
      </label>
      {error && <p className="cc-error" role="alert">{error}</p>}
      {working && <p className="hint lm-status" role="status">Adding to the map…</p>}

      {map === null ? <p className="hint">Loading…</p> : empty ? (
        <p className="hint lm-empty">
          Your map starts when the coach teaches something. Each idea becomes a branch you can tap to go deeper.
        </p>
      ) : (
        <Tree map={map} layout="v" fresh={fresh} disabled={busy} onAsk={onAsk} />
      )}

      <div className="lm-actions">
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => update(null)} disabled={working}>
          {empty ? "Build it from this lesson" : "Update from this lesson"}
        </button>
        {!empty && map && (
          <>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setExpanded(true)}>Expand</button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => onSave(mapOutline(map), `${map.title || "Lesson"}: map`)}>Save to study folder</button>
            <button type="button" className="sg-link" onClick={clear}>Clear</button>
          </>
        )}
      </div>

      {expanded && map && (
        <div className="rp-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) setExpanded(false); }}>
          <div className="rp-dialog lm-dialog" role="dialog" aria-modal="true" aria-label="Lesson map">
            <header className="rp-head">
              <div>
                <h2 className="rp-title">Lesson map</h2>
                <p className="hint">Tap a branch or point to ask the coach to go deeper.</p>
              </div>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setExpanded(false)}>Close</button>
            </header>
            <div className="lm-scroll">
              <Tree map={map} layout="h" fresh={fresh} disabled={busy} onAsk={ask} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
