"use client";

import { useEffect, useState } from "react";
import { api, DiscountCodeCheck, Usage, User } from "@/lib/api";

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

  // Discount code box. A checked code is previewed first; "stripe" codes
  // ride along with the upgrade click, "free_days" codes are redeemed.
  const [codeInput, setCodeInput] = useState("");
  const [applied, setApplied] = useState<{ code: string; check: DiscountCodeCheck } | null>(null);
  const [checking, setChecking] = useState(false);
  const [notice, setNotice] = useState("");

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
      const withCode = applied?.check.kind === "stripe" ? { code: applied.code } : undefined;
      const { checkout_url } = await api<{ checkout_url: string }>("/billing/subscribe", {
        method: "POST", ...(withCode ? { body: JSON.stringify(withCode) } : {}),
      });
      window.location.href = checkout_url;
    } catch (err: any) {
      setError(err.message || "Couldn't start checkout. Try again in a moment.");
      setLoadingAction(false);
    }
  }

  async function applyCode() {
    const code = codeInput.trim();
    if (!code || checking) return;
    setChecking(true);
    setError("");
    setNotice("");
    try {
      const check = await api<DiscountCodeCheck>("/billing/check-code", { method: "POST", body: JSON.stringify({ code }) });
      setApplied({ code, check });
    } catch (err: any) {
      setApplied(null);
      setError(/too many/i.test(err.message || "") ? "Too many attempts — please wait a while and try again." : (err.message || "That code isn't valid or has expired."));
    } finally {
      setChecking(false);
    }
  }

  async function redeemCode() {
    if (!applied || applied.check.kind !== "free_days" || loadingAction) return;
    setLoadingAction(true);
    setError("");
    try {
      await api("/billing/redeem-code", { method: "POST", body: JSON.stringify({ code: applied.code }) });
      setNotice(`Done — ${applied.check.description}.`);
      setApplied(null);
      setCodeInput("");
      await load();
    } catch (err: any) {
      setError(err.message || "Couldn't redeem that code.");
    } finally {
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
  const hasPaidSub = user?.subscription_tier === "pro" && user?.subscription_status === "active";
  const proUntil = user?.pro_until ? new Date(user.pro_until + (user.pro_until.endsWith("Z") ? "" : "Z")) : null;
  const complimentary = isPro && !hasPaidSub && !!proUntil && proUntil.getTime() > Date.now();

  return (
    <div>
      <h1>Billing</h1>

      {error && <p className="error-text">{error}</p>}
      {notice && <p className="muted" style={{ color: "var(--accent-hover)" }}>{notice}</p>}

      <div className="card" style={isPro ? { borderColor: "var(--accent)" } : {}}>
        <div className="card-row">
          <div>
            <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {isPro ? "Riseply Pro" : "Free plan"}
              {isPro && <span className="pill pill-approved">Active</span>}
            </h3>
            {!isPro && <p className="muted">You're on the free plan.</p>}
            {isPro && !complimentary && <p className="muted">Thanks for supporting Riseply.</p>}
            {complimentary && proUntil && (
              <p className="muted">Complimentary Pro access until {proUntil.toLocaleDateString()}. Subscribe any time to keep it going.</p>
            )}
          </div>
          {isPro && !complimentary ? (
            <button className="btn btn-ghost btn-sm" onClick={manageSubscription} disabled={loadingAction}>
              Manage subscription
            </button>
          ) : (
            <button className="btn btn-primary" onClick={upgrade} disabled={loadingAction}>
              {loadingAction ? "Loading…" : complimentary ? "Subscribe to keep Pro — $9.99/mo" : "Upgrade to Pro — $9.99/mo"}
            </button>
          )}
        </div>

        {applied?.check.kind === "stripe" && !hasPaidSub && (
          <p className="muted" style={{ marginTop: 12 }}>
            Code <strong>{applied.code.toUpperCase()}</strong> will be applied at checkout: {applied.check.description}.
          </p>
        )}

        {!isPro && (
          <ul style={{ marginTop: 16, paddingLeft: 20, fontSize: "0.9rem" }}>
            {PRO_FEATURES.map((f) => <li key={f} style={{ marginBottom: 6 }}>{f}</li>)}
          </ul>
        )}
      </div>

      {!hasPaidSub && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Have a discount code?</h3>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input
              placeholder="Enter code" value={codeInput} maxLength={60} style={{ flex: "1 1 200px" }}
              onChange={(e) => { setCodeInput(e.target.value); setApplied(null); }}
              onKeyDown={(e) => { if (e.key === "Enter") applyCode(); }}
            />
            <button className="btn btn-ghost" onClick={applyCode} disabled={!codeInput.trim() || checking}>
              {checking ? "Checking…" : "Apply"}
            </button>
          </div>
          {applied?.check.kind === "free_days" && (
            <div style={{ marginTop: 12 }}>
              <p className="muted" style={{ marginTop: 0 }}>This code gives you {applied.check.description}.</p>
              <button className="btn btn-primary btn-sm" onClick={redeemCode} disabled={loadingAction}>
                {loadingAction ? "Redeeming…" : "Redeem"}
              </button>
            </div>
          )}
          {applied?.check.kind === "stripe" && (
            <p className="muted" style={{ marginBottom: 0 }}>
              Good to go: {applied.check.description}. Click Upgrade above to use it.
            </p>
          )}
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
