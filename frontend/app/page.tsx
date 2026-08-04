"use client";

import Link from "next/link";

export default function HomePage() {
  return (
    <div className="auth-shell">
      <div style={{ textAlign: "center", maxWidth: 480 }}>
        <h1 style={{ fontStyle: "italic" }}>Job Agent</h1>
        <p className="muted" style={{ marginBottom: 28 }}>
          Finds roles that fit, tailors your resume for each one, and waits
          for your OK before anything gets submitted.
        </p>
        <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
          <Link href="/login" className="btn btn-ghost">Log in</Link>
          <Link href="/signup" className="btn btn-primary">Get started</Link>
        </div>
        <p className="muted" style={{ marginTop: 28, fontSize: "0.8rem" }}>
          <Link href="/terms">Terms of Service</Link> · <Link href="/privacy">Privacy Policy</Link>
        </p>
      </div>
    </div>
  );
}
