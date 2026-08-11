"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { setQuotaLimitListener } from "@/lib/api";

/**
 * A real, hard-to-miss modal for "you've hit a plan limit" -- built
 * directly from user feedback: someone hit their monthly match quota
 * (and separately, the 1-search-profile limit) and had no idea why
 * nothing was happening, because the only signal was a small inline
 * error line easy to miss or scroll past. Registers itself as the
 * single global listener for any 429 from api() (see lib/api.ts), plus
 * pages can call showQuotaLimitModal() directly for the one quota
 * signal that isn't a 429 at all (/pipeline/match returns 200 with
 * usage_limit_reached: true when it stops early mid-run, so it can
 * still show partial results).
 *
 * Rendered once, at the dashboard layout level -- not per-page.
 */
export default function QuotaLimitModal() {
  const [message, setMessage] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    setQuotaLimitListener((msg) => setMessage(msg));
    return () => setQuotaLimitListener(null);
  }, []);

  if (!message) return null;

  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(22, 35, 61, 0.45)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
      }}
      onClick={() => setMessage(null)}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="card"
        style={{ maxWidth: 420, width: "90%", textAlign: "center" }}
      >
        <div style={{ fontSize: 32, marginBottom: 8 }}>⏳</div>
        <h3 style={{ marginTop: 0 }}>You've hit your plan's limit</h3>
        <p className="muted" style={{ marginBottom: 20 }}>{message}</p>
        <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
          <button className="btn btn-ghost" onClick={() => setMessage(null)}>Got it</button>
          <button
            className="btn btn-primary"
            onClick={() => { setMessage(null); router.push("/dashboard/billing"); }}
          >
            View plans
          </button>
        </div>
      </div>
    </div>
  );
}
