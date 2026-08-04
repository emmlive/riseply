"use client";

import { useEffect, useState } from "react";
import { api, CompanyStats, RiseIndexMe } from "@/lib/api";

export default function RiseIndexPage() {
  const [me, setMe] = useState<RiseIndexMe | null>(null);
  const [trending, setTrending] = useState<CompanyStats[]>([]);
  const [barsVisible, setBarsVisible] = useState(false);

  useEffect(() => {
    api<RiseIndexMe>("/rise-index/me").then(setMe);
    api<CompanyStats[]>("/rise-index/trending").then((data) => {
      setTrending(data);
      // Bars start at 0 and animate in on mount -- the "live number"
      // feel is the whole point.
      requestAnimationFrame(() => requestAnimationFrame(() => setBarsVisible(true)));
    });
  }, []);

  return (
    <div>
      <h1>Rise Index</h1>
      <p className="muted">
        Live, anonymized response-rate data pulled from everyone using
        Riseply — not just you. Companies only show up once enough people
        have applied to keep individual applicants unidentifiable.
      </p>

      {me && (
        <div className="rise-hero">
          <div className="rise-stat">
            <div className="value">{me.rise_points}</div>
            <div className="label">Rise points</div>
          </div>
          <div className="rise-stat">
            <div className="value">
              <span className="streak-flame">🔥</span> {me.current_streak}
            </div>
            <div className="label">Day streak</div>
          </div>
          <div className="rise-stat">
            <div className="value">{me.longest_streak}</div>
            <div className="label">Longest streak</div>
          </div>
        </div>
      )}

      <h2 style={{ marginTop: 8 }}>Trending companies</h2>
      <p className="muted" style={{ marginTop: -8, fontSize: "0.85rem" }}>
        By application volume in the last 14 days
      </p>

      {trending.length === 0 && (
        <div className="empty-state">
          Not enough activity yet to show trends — this fills in as more
          people apply through Riseply.
        </div>
      )}

      {trending.length > 0 && (
        <div className="card">
          {trending.map((c) => (
            <div key={c.company} className="company-stat-row">
              <div className="company-stat-name">{c.company}</div>
              <div className="response-bar-track">
                <div
                  className="response-bar-fill"
                  style={{ width: barsVisible ? `${c.response_rate}%` : "0%" }}
                />
              </div>
              <div className="company-stat-pct">{c.response_rate}%</div>
              <div className="company-stat-meta">
                {c.applied_count} applicants
                {c.avg_days_to_respond !== null && ` · ~${c.avg_days_to_respond}d to hear back`}
              </div>
            </div>
          ))}
        </div>
      )}

      {me && me.recent_events.length > 0 && (
        <>
          <h2 style={{ marginTop: 28 }}>Your recent activity</h2>
          <div className="card">
            {me.recent_events.map((e, i) => (
              <div key={i} className="points-event-row">
                <span>{e.reason}</span>
                <span className="points-event-amount">+{e.amount}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
