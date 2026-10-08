"use client";

import { useEffect, useState } from "react";
import { AdminFeedback, AdminFeedbackSummary, api, formatWhen } from "@/lib/api";

// Admin: everything people have said in-product, newest first.
const KIND_LABEL = { general: "Feedback button", coach_reply: "Coach reply" } as const;
const CATEGORY_LABEL: Record<string, string> = { idea: "Idea", problem: "Something's broken", praise: "Something they like" };

export default function FeedbackTab({ canAct }: { canAct: boolean }) {
  const [rows, setRows] = useState<AdminFeedback[]>([]);
  const [summary, setSummary] = useState<AdminFeedbackSummary | null>(null);
  const [kind, setKind] = useState<"" | "general" | "coach_reply">("");
  const [status, setStatus] = useState<"" | "new" | "reviewed">("new");
  const [low, setLow] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<number | null>(null);

  async function load() {
    setLoading(true);
    setError("");
    const q = new URLSearchParams();
    if (kind) q.set("kind", kind);
    if (status) q.set("status", status);
    if (low) q.set("low", "true");
    try {
      const [list, sum] = await Promise.all([
        api<AdminFeedback[]>(`/admin/feedback?${q.toString()}`),
        api<AdminFeedbackSummary>("/admin/feedback/summary"),
      ]);
      setRows(list);
      setSummary(sum);
    } catch (e: any) {
      setError(e?.message || "Couldn't load feedback.");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [kind, status, low]);

  async function mark(id: number, next: "new" | "reviewed") {
    setBusy(id);
    try {
      await api(`/admin/feedback/${id}/status?status=${next}`, { method: "POST" });
      await load();
    } catch (e: any) {
      setError(e?.message || "Couldn't update that.");
    } finally {
      setBusy(null);
    }
  }

  const helpfulPct = summary && summary.thumbs_up + summary.thumbs_down > 0
    ? Math.round((100 * summary.thumbs_up) / (summary.thumbs_up + summary.thumbs_down)) : null;

  return (
    <div>
      {summary && (
        <div className="pg-tiles" style={{ marginTop: 0 }}>
          <div className="pg-tile"><div className="pg-tile-label">New to review</div><div className="pg-tile-value">{summary.new}</div><div className="pg-tile-sub">of {summary.total} total</div></div>
          <div className="pg-tile"><div className="pg-tile-label">Average rating</div><div className="pg-tile-value">{summary.avg_rating ?? "—"}</div><div className="pg-tile-sub">{summary.rated} rating{summary.rated === 1 ? "" : "s"} out of 5</div></div>
          <div className="pg-tile"><div className="pg-tile-label">Coach replies helpful</div><div className="pg-tile-value">{helpfulPct !== null ? `${helpfulPct}%` : "—"}</div><div className="pg-tile-sub">{summary.thumbs_up} up, {summary.thumbs_down} down</div></div>
        </div>
      )}

      <div className="fb-filters">
        <select className="cc-input" aria-label="Type" value={kind} onChange={(e) => setKind(e.target.value as any)}>
          <option value="">All types</option><option value="general">Feedback button</option><option value="coach_reply">Coach replies</option>
        </select>
        <select className="cc-input" aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value as any)}>
          <option value="new">New</option><option value="reviewed">Reviewed</option><option value="">All</option>
        </select>
        <label className="cc-check"><input type="checkbox" checked={low} onChange={(e) => setLow(e.target.checked)} /> Needs attention (1 to 2 stars, thumbs down)</label>
      </div>

      {error && <p className="cc-error" role="alert">{error}</p>}
      {loading && <p className="hint">Loading…</p>}
      {!loading && rows.length === 0 && <div className="empty-state">Nothing here{status === "new" ? " that needs review" : ""}.</div>}

      {rows.map((r) => (
        <div key={r.id} className="card fb-row">
          <div className="fb-row-head">
            <div>
              {r.rating !== null && <span className="fb-row-stars" aria-label={`${r.rating} out of 5`}>{"★".repeat(r.rating)}<span className="fb-dim">{"★".repeat(5 - r.rating)}</span></span>}
              {r.helpful !== null && <strong>{r.helpful ? "Helpful" : "Not helpful"}</strong>}
              {r.category && <span className="fb-chip">{CATEGORY_LABEL[r.category] || r.category}</span>}
              <span className="fb-chip fb-chip-plain">{KIND_LABEL[r.kind]}</span>
            </div>
            <div className="hint">{formatWhen(r.created_at)}</div>
          </div>
          {r.message && <p className="fb-row-msg">{r.message}</p>}
          {r.reply_excerpt && (
            <details className="fb-excerpt">
              <summary>The coach reply they rated</summary>
              <p>{r.reply_excerpt}</p>
            </details>
          )}
          <div className="fb-row-foot">
            <span className="hint">{r.user_email}{r.page ? `, from ${r.page}` : ""}</span>
            {canAct && (
              <button className="btn btn-ghost btn-sm" disabled={busy === r.id} onClick={() => mark(r.id, r.status === "new" ? "reviewed" : "new")}>
                {r.status === "new" ? "Mark reviewed" : "Mark as new"}
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
