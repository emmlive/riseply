"use client";

import Link from "next/link";

const FEATURES = [
  { label: "Find", desc: "Matches roles to your resume, scored by AI" },
  { label: "Tailor", desc: "Rewrites your resume per job — nothing invented" },
  { label: "Prep", desc: "Interview questions and an onboarding plan" },
  { label: "Rise", desc: "Live response-rate data from everyone using it" },
];

export default function HomePage() {
  return (
    <div className="auth-shell">
      <div style={{ textAlign: "center", maxWidth: 560 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, marginBottom: 4 }}>
          <img src="/brand/icon.svg" alt="" width={40} height={40} />
          <h1 style={{ fontStyle: "italic", margin: 0 }}>Riseply</h1>
        </div>
        <p className="muted" style={{ marginBottom: 8 }}>
          Riseply finds roles that fit, tailors your resume for each one,
          preps you for interviews, and helps you settle into your first
          weeks once you land it — all while you stay in control. Nothing
          goes out without your OK.
        </p>

        <div style={{
          display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 12,
          margin: "24px 0", textAlign: "left",
        }}>
          {FEATURES.map((f) => (
            <div key={f.label} style={{
              background: "var(--surface)", border: "1px solid var(--border)",
              borderRadius: 10, padding: "12px 14px",
            }}>
              <div style={{ fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: "0.95rem", marginBottom: 4 }}>
                {f.label}
              </div>
              <div className="hint" style={{ lineHeight: 1.4 }}>{f.desc}</div>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
          <Link href="/login" className="btn btn-ghost">Log in</Link>
          <Link href="/signup" className="btn btn-primary">Get started</Link>
        </div>
        <p className="muted" style={{ marginTop: 28, fontSize: "0.8rem" }}>
          <Link href="/terms">Terms of Service</Link> · <Link href="/privacy">Privacy Policy</Link> · <Link href="/security">Security & Trust</Link>
        </p>
      </div>
    </div>
  );
}
