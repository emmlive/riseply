"use client";

import { useEffect, useState } from "react";
import { api, Usage, User } from "@/lib/api";

const PRO_FEATURES = [
  "5x higher monthly limits on matching, tailoring, prep, and Job Buddy",
  "Up to 10 simultaneous search profiles (free is capped at 1)",
  "Priority access to new features as they ship",
];

export default function BillingPage() {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loadingAction, setLoadingAction] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    const [u, me] = await Promise.all([api<Usage>("/usage"), api<User>("/me")]);
    setUsage(u);
    setUser(me);
  }

  useEffect(() => { load(); }, []);

  async function upgrade() {
    setLoadingAction(true);
    setError("");
    try {
      const { checkout_url } = await api<{ checkout_url: string }>("/billing/subscribe", { method: "POST" });
      window.location.href = checkout_url;
    } catch (err: any) {
      setError(err.message || "Couldn't start checkout. Try again in a moment.");
      setLoadingAction(false);
    }
  }

  async function manageSubscription() {
    setLoadingAction(true);
    setError("");
    try {
      const { portal_url } = await api<{ portal_url: string }>("/billing/portal", { method: "POST" });
      window.location.href = portal_url;
    } catch (err: any) {
      setError(err.message || "Couldn't open the billing portal. Try again in a moment.");
      setLoadingAction(false);
    }
  }

  const isPro = usage?.tier === "pro";

  return (
    <div>
      <h1>Billing</h1>

      {error && <p className="error-text">{error}</p>}

      <div className="card" style={isPro ? { borderColor: "var(--accent)" } : {}}>
        <div className="card-row">
          <div>
            <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {isPro ? "Riseply Pro" : "Free plan"}
              {isPro && <span className="pill pill-approved">Active</span>}
            </h3>
            {!isPro && <p className="muted">You're on the free plan.</p>}
            {isPro && <p className="muted">Thanks for supporting Riseply.</p>}
          </div>
          {isPro ? (
            <button className="btn btn-ghost btn-sm" onClick={manageSubscription} disabled={loadingAction}>
              Manage subscription
            </button>
          ) : (
            <button className="btn btn-primary" onClick={upgrade} disabled={loadingAction}>
              {loadingAction ? "Loading…" : "Upgrade to Pro — $9.99/mo"}
            </button>
          )}
        </div>

        {!isPro && (
          <ul style={{ marginTop: 16, paddingLeft: 20, fontSize: "0.9rem" }}>
            {PRO_FEATURES.map((f) => <li key={f} style={{ marginBottom: 6 }}>{f}</li>)}
          </ul>
        )}
      </div>

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
