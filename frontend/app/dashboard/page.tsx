"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Application, Usage, RiseIndexMe, NearMiss } from "@/lib/api";

export default function OverviewPage() {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [pending, setPending] = useState<Application[]>([]);
  const [rise, setRise] = useState<RiseIndexMe | null>(null);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [nearMisses, setNearMisses] = useState<NearMiss[]>([]);

  async function load() {
    try {
      const [u, apps, r] = await Promise.all([
        api<Usage>("/usage"),
        api<Application[]>("/applications?status=pending_approval"),
        api<RiseIndexMe>("/rise-index/me"),
      ]);
      setUsage(u);
      setPending(apps);
      setRise(r);
    } catch {
      // handled globally by api() redirecting to /login on 401
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function runPipeline() {
    setRunning(true);
    setError("");
    setMessage("");
    setNearMisses([]);
    try {
      await api("/pipeline/discover", { method: "POST" });
      const result = await api<{ queued_application_ids: number[]; usage_limit_reached: boolean; near_misses: NearMiss[]; hit_job_cap: boolean }>(
        "/pipeline/match",
        { method: "POST" }
      );
      setMessage(
        result.queued_application_ids.length > 0
          ? `Found ${result.queued_application_ids.length} new match${result.queued_application_ids.length === 1 ? "" : "es"} — check your email or the Applications tab.`
          : result.near_misses.length > 0
          ? "Nothing quite cleared your bar this run — here's what came closest."
          : "No new matches this run. Try again later as new postings come in."
      );
      if (result.usage_limit_reached) {
        setMessage((m) => m + " (Stopped early — monthly match limit reached.)");
      } else if (result.hit_job_cap) {
        setMessage((m) => m + " There are more unscored postings waiting — click \"Find new matches\" again to keep going, or check back after the nightly search runs.");
      }
      setNearMisses(result.near_misses);
      load();
    } catch (err: any) {
      setError(err.message || "Something went wrong running the search.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <div className="topbar">
        <h1>Overview</h1>
        <div style={{ textAlign: "right" }}>
          <button className="btn btn-primary" onClick={runPipeline} disabled={running}>
            {running ? "Searching…" : "Find new matches"}
          </button>
          {running && (
            <p className="hint" style={{ marginTop: 6, marginBottom: 0 }}>
              Scoring postings one at a time — this can take up to a minute or two.
            </p>
          )}
        </div>
      </div>

      {message && (
        <div className="card" style={{ borderColor: "var(--accent)" }}>
          {message}
        </div>
      )}
      {error && <p className="error-text">{error}</p>}

      {nearMisses.length > 0 && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Closest this run</h3>
          <p className="hint" style={{ marginTop: -4, marginBottom: 12 }}>
            None of these cleared your profile's match threshold, but they were the nearest —
            worth a look, or a sign to loosen your search criteria a bit.
          </p>
          {nearMisses.map((nm, i) => (
            <div key={i} className="points-event-row">
              <div>
                <div style={{ fontWeight: 600 }}>{nm.title} — {nm.company}</div>
                <div className="hint">{nm.reason}</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className="ticket">match <span className="score">{nm.score}%</span></span>
                <a href={nm.url} target="_blank" rel="noopener noreferrer" className="hint">View →</a>
              </div>
            </div>
          ))}
        </div>
      )}

      {rise && (
        <div className="rise-hero">
          <div className="rise-stat">
            <div className="value">
              <span className="streak-flame">🔥</span> {rise.current_streak}
            </div>
            <div className="label">Day streak</div>
          </div>
          <div className="rise-stat">
            <div className="value">{rise.rise_points}</div>
            <div className="label">Rise points</div>
          </div>
          <Link href="/dashboard/rise-index" className="rise-stat" style={{ textDecoration: "none", color: "inherit", display: "flex", flexDirection: "column", justifyContent: "center" }}>
            <div className="label" style={{ color: "var(--accent-hover)", fontWeight: 600 }}>See trending companies →</div>
          </Link>
        </div>
      )}

      {usage && (
        <div className="card">
          <h3>This month's usage</h3>
          <div style={{ display: "flex", gap: 32, marginTop: 10, flexWrap: "wrap" }}>
            <UsageBar label="Job matches scored" used={usage.matches_used} limit={usage.matches_limit} />
            <UsageBar label="Resumes tailored" used={usage.tailored_resumes_used} limit={usage.tailored_resumes_limit} />
            <UsageBar label="Interview preps" used={usage.interview_preps_used} limit={usage.interview_preps_limit} />
            <UsageBar label="Job Buddy messages" used={usage.job_buddy_messages_used} limit={usage.job_buddy_messages_limit} />
          </div>
        </div>
      )}

      <h2 style={{ marginTop: 28 }}>Awaiting your review</h2>
      {pending.length === 0 ? (
        <div className="empty-state">
          No applications waiting on you right now. Run a search, or check back later.
        </div>
      ) : (
        pending.slice(0, 5).map((app) => (
          <div key={app.id} className="card">
            <div className="card-row">
              <div>
                <h3>{app.job_title} — {app.job_company}</h3>
                <p className="muted" style={{ margin: 0 }}>{app.job_location}</p>
              </div>
              <span className={`ticket ${app.match_score >= 80 ? "high" : ""}`}>
                match <span className="score">{app.match_score}%</span>
              </span>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

function UsageBar({ label, used, limit }: { label: string; used: number; limit: number }) {
  const pct = Math.min(100, Math.round((used / Math.max(limit, 1)) * 100));
  return (
    <div style={{ flex: "1 1 180px", minWidth: 180 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.82rem" }}>
        <span className="muted">{label}</span>
        <span className="mono">{used} / {limit}</span>
      </div>
      <div style={{ height: 6, background: "var(--paper)", borderRadius: 4, marginTop: 6, overflow: "hidden" }}>
        <div style={{
          width: `${pct}%`, height: "100%",
          background: pct >= 90 ? "var(--danger)" : "var(--accent)",
        }} />
      </div>
    </div>
  );
}
