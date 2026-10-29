"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { StudyDraft } from "@/components/SaveToStudy";
import "./DefineLookup.css";

interface Defined { term: string; meaning: string; example: string; related: string[] }
interface Picked { text: string; context: string; x: number; y: number }

const SCOPE = "[data-define-scope]";

// What the person is reading around the picked words, so the meaning fits.
function contextAround(range: Range, term: string): string {
  const bubble = (range.commonAncestorContainer.nodeType === 1
    ? (range.commonAncestorContainer as Element)
    : range.commonAncestorContainer.parentElement)?.closest(".cc-bubble");
  const text = (bubble?.textContent || "").replace(/\s+/g, " ");
  const at = text.indexOf(term);
  if (at < 0) return text.slice(0, 600);
  return text.slice(Math.max(0, at - 300), at + term.length + 300);
}

// "What does this mean?": pick words in the lesson (or type them) and get a
// short plain-language meaning, an example, and related words to look up next.
// Nothing is sent until the person asks.
export default function DefineLookup({ topic, sessionId, onSave }: {
  topic: string;
  sessionId: number | null;
  onSave?: (draft: StudyDraft) => void;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [context, setContext] = useState("");
  const [res, setRes] = useState<Defined | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [picked, setPicked] = useState<Picked | null>(null);
  const seq = useRef(0);

  const run = useCallback(async (term: string, ctx: string) => {
    const t = term.replace(/\s+/g, " ").trim();
    if (t.length < 2) return;
    const mine = ++seq.current;
    setOpen(true); setQ(t); setContext(ctx); setBusy(true); setError(""); setRes(null); setPicked(null);
    try {
      const out = await api<Defined>("/career-coach/define", { method: "POST", body: JSON.stringify({ term: t, context: ctx, topic }) });
      if (mine === seq.current) setRes(out);
    } catch (e) {
      if (mine === seq.current) setError(e instanceof Error ? e.message : "Couldn't look that up. Try again.");
    } finally {
      if (mine === seq.current) setBusy(false);
    }
  }, [topic]);

  // Watch for words picked inside the lesson text.
  useEffect(() => {
    function check() {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || sel.rangeCount === 0) { setPicked(null); return; }
      const text = sel.toString().replace(/\s+/g, " ").trim();
      const range = sel.getRangeAt(0);
      const host = (range.commonAncestorContainer.nodeType === 1 ? range.commonAncestorContainer as Element : range.commonAncestorContainer.parentElement);
      if (!host || !host.closest(SCOPE) || text.length < 2 || text.length > 100 || text.split(" ").length > 10) { setPicked(null); return; }
      const r = range.getBoundingClientRect();
      setPicked({ text, context: contextAround(range, text), x: Math.min(Math.max(r.left + r.width / 2, 110), window.innerWidth - 110), y: Math.max(r.top - 8, 48) });
    }
    const soon = () => setTimeout(check, 10);
    document.addEventListener("mouseup", soon);
    document.addEventListener("keyup", soon);
    document.addEventListener("touchend", soon);
    return () => {
      document.removeEventListener("mouseup", soon);
      document.removeEventListener("keyup", soon);
      document.removeEventListener("touchend", soon);
    };
  }, []);

  function save() {
    if (!res || !onSave) return;
    onSave({
      title: res.term,
      content: `${res.term}\n\n${res.meaning}${res.example ? `\n\nExample: ${res.example}` : ""}`,
      source: "manual",
      sourceLabel: "Word lookup",
      sessionId,
    });
  }

  return (
    <>
      <div className="cc-define-bar">
        {!open && (
          <button className="btn btn-ghost btn-sm" onClick={() => setOpen(true)}>
            📖 Look up a word
          </button>
        )}
        {open && (
          <div className="cc-define-panel">
            <form onSubmit={(e) => { e.preventDefault(); run(q, q === res?.term ? context : ""); }} className="cc-define-form">
              <input value={q} onChange={(e) => setQ(e.target.value)} maxLength={100} placeholder="A word or phrase from the lesson, like SWIFT infrastructure"
                     aria-label="Word or phrase to look up" autoFocus />
              <button className="btn btn-primary btn-sm" disabled={busy || q.trim().length < 2}>{busy ? "Looking…" : "What does it mean?"}</button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setOpen(false); setRes(null); setError(""); }}>Close</button>
            </form>
            <p className="muted cc-define-hint">Tip: select any words in the lesson and press the button that appears.</p>
            {error && <p className="cc-define-error" role="alert">{error}</p>}
            {res && (
              <div className="cc-define-card">
                <strong>{res.term}</strong>
                <p>{res.meaning}</p>
                {res.example && <p className="muted">For example: {res.example}</p>}
                {res.related.length > 0 && (
                  <div className="cc-chips" aria-label="Related words">
                    {res.related.map((r) => (
                      <button key={r} className="btn btn-ghost btn-sm" onClick={() => run(r, "")}>{r}</button>
                    ))}
                  </div>
                )}
                {onSave && <button className="btn btn-ghost btn-sm" onClick={save}>Save to study notes</button>}
              </div>
            )}
          </div>
        )}
      </div>
      {picked && (
        <button className="cc-define-float" style={{ left: picked.x, top: picked.y }}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => run(picked.text, picked.context)}>
          📖 What does “{picked.text.length > 32 ? picked.text.slice(0, 30) + "…" : picked.text}” mean?
        </button>
      )}
    </>
  );
}
