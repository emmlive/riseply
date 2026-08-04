"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) });
      setSent(true);
    } catch (err: any) {
      setError(err.message || "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <h2>Reset your password</h2>

        {sent ? (
          <>
            <p>
              If an account exists for <strong>{email}</strong>, we've sent
              a password reset link — check your inbox.
            </p>
            <p className="muted" style={{ fontSize: "0.85rem" }}>
              The link expires in 30 minutes and can only be used once.
            </p>
          </>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="field">
              <label htmlFor="email">Email</label>
              <input id="email" type="email" required value={email}
                     onChange={(e) => setEmail(e.target.value)} />
            </div>
            {error && <p className="error-text">{error}</p>}
            <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
              {loading ? "Sending…" : "Send reset link"}
            </button>
          </form>
        )}

        <p className="muted" style={{ marginTop: 18, fontSize: "0.88rem" }}>
          <Link href="/login">← Back to log in</Link>
        </p>
      </div>
    </div>
  );
}
