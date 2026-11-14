"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApplyQueue, ApplyQueueItem } from "@/lib/api";

// The person's strongest open matches, best first, each with its tailored
// resume already made. They open the job, let the extension's Autofill fill
// the form, check it and submit, then come back and mark it applied. That
// works on every site, LinkedIn included, because the person clicks Submit.

export default function ApplyQueuePage() {
  const [data, setData] = useState<ApplyQueue | null>(null);
  const [busy, setBusy] = useState(0);
  const [error, setError] = useState("");

  function load() {
    api<ApplyQueue>("/applications/apply-queue").then(setData).catch((e) => setError(e.message || "Couldn't load your queue."));
  }
  useEffect(load, []);

  async function act(item: ApplyQueueItem, action: "mark-submitted" | "reject") {
    if (busy) return;
    setBusy(item.id); setError("");
    try {
      await api(`/applications/${item.id}/${action}`, { method: "POST", ...(action === "reject" ? { body: JSON.stringify({}) } : {}) });
      load();
    } catch (e: any) { setError(e.message || "Couldn't save that. Try again."); }
    finally { setBusy(0); }
  }

  if (!data) return <p className="muted">{error || "Loading…"}</p>;

  return (
    <div className="aq">
      <h1>Apply queue</h1>
      <p className="muted">
        Your best open matches, with a resume already tailored for each. Open a job, click Riseply Autofill in the extension,
        check the form and submit. Then come back and press <strong>I applied</strong>. This works on every site, LinkedIn included,
        because you click Submit. Want it hands-off on supported sites? Turn on <Link href="/dashboard/profile">Autopilot in Profile</Link>.
      </p>
      <p className="aq-week">
        <strong>{data.applied_this_week}</strong> applied in the last 7 days
        {data.autopilot_applied_this_week > 0 && <> ({data.autopilot_applied_this_week} by Autopilot)</>}.
      </p>
      {error && <p className="cc-error" role="alert">{error}</p>}

      {data.items.length === 0 && (
        <div className="card"><p style={{ margin: 0 }}>Nothing waiting. New strong matches appear here as Riseply finds them. You can also run <Link href="/dashboard/profiles">a search</Link> now.</p></div>
      )}

      {data.items.map((it) => (
        <div className="card aq-item" key={it.id}>
          <div className="aq-head">
            <div>
              <h3>{it.title}</h3>
              <p className="muted" style={{ margin: 0 }}>{it.company}{it.location ? ` · ${it.location}` : ""}</p>
            </div>
            <span className={it.match_score >= 80 ? "pill pill-approved" : "pill pill-default"}>{it.match_score}% match</span>
          </div>
          {it.match_reason && <p>{it.match_reason}</p>}
          <p className="aq-tags">
            <span className={it.has_resume ? "pill pill-approved" : "pill pill-default"}>{it.has_resume ? "Tailored resume ready" : "Base resume (tailor it in Applications)"}</span>{" "}
            {it.autopilot_ok && <span className="pill pill-submitted">Autopilot can apply here</span>}
          </p>
          {it.note && <p className="hint">{it.note}</p>}
          <div className="aq-actions">
            <a className="btn btn-primary btn-sm" href={it.url} target="_blank" rel="noopener noreferrer">Open job</a>
            <button className="btn btn-ghost btn-sm" disabled={busy === it.id} onClick={() => act(it, "mark-submitted")}>I applied</button>
            <button className="btn btn-ghost btn-sm" disabled={busy === it.id} onClick={() => act(it, "reject")}>Not for me</button>
            <Link className="btn btn-ghost btn-sm" href="/dashboard/applications">Review resume</Link>
          </div>
        </div>
      ))}
    </div>
  );
}
