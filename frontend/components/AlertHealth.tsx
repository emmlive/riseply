"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

// "Are my alerts working?" -- the answer from Riseply's own records: what is
// set up, what is delivering, and whether the daily search is running. Each
// problem says what to do. Nothing here changes any setting by itself.

type Check = { id: string; ok: boolean; tip: boolean; title: string; detail: string; fix_href: string; fix_label: string };
type Status = { headline: string; ok: boolean; checks: Check[] };

const DISCORD_RESULT: Record<string, string> = {
  sent: "Discord: sent.",
  not_connected: "Discord: not connected, so nothing was sent there.",
  alerts_off: "Discord: connected, but job alerts are switched off for it.",
  failed: "Discord: couldn't deliver. See the check below.",
};

export default function AlertHealth() {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [testing, setTesting] = useState(false);
  const [testMsg, setTestMsg] = useState("");

  function load() {
    api<Status>("/me/alerts/status").then((s) => { setStatus(s); setError(""); })
      .catch((e: any) => setError(e?.message || "Couldn't check your alerts."));
  }
  useEffect(load, []);

  async function sendTest() {
    setTesting(true); setTestMsg("");
    try {
      const r = await api<{ sent_to: string; discord: string }>("/me/alerts/preview", { method: "POST" });
      setTestMsg(`Email: sent to ${r.sent_to}. ${DISCORD_RESULT[r.discord] || ""}`);
      load();
    } catch (e: any) { setTestMsg(e?.message || "Couldn't send the test."); }
    setTesting(false);
  }

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3 style={{ marginTop: 0 }}>Are my alerts working?</h3>
      {error && <p className="error-text">{error}</p>}
      {!status && !error && <p className="muted">Checking…</p>}
      {status && (
        <>
          <p style={{ fontWeight: 600, color: status.ok ? "var(--accent)" : "var(--danger)" }}>{status.headline}</p>
          <ul style={{ listStyle: "none", padding: 0, margin: "8px 0 12px" }}>
            {status.checks.map((c) => (
              <li key={c.id} style={{ display: "flex", gap: 10, padding: "8px 0", borderTop: "1px solid var(--border)" }}>
                <span aria-hidden style={{ width: 18, fontWeight: 700, color: c.ok ? "var(--accent)" : c.tip ? "var(--ink-muted)" : "var(--danger)" }}>
                  {c.ok ? "✓" : c.tip ? "•" : "✗"}
                </span>
                <span style={{ flex: 1 }}>
                  <strong>{c.title}</strong>
                  <span className="hint" style={{ display: "block", margin: "2px 0 0" }}>{c.detail}</span>
                  {!c.ok && c.fix_href && (
                    <Link href={c.fix_href} style={{ fontWeight: 600, fontSize: 13 }}>{c.fix_label}</Link>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      <button type="button" className="btn btn-ghost btn-sm" disabled={testing} onClick={sendTest}>
        {testing ? "Sending…" : "Send a test to email and Discord"}
      </button>
      {testMsg && <p className="hint">{testMsg}</p>}
    </div>
  );
}
