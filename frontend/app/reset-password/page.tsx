"use client";

import { Suspense, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, clearToken } from "@/lib/api";

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordContent />
    </Suspense>
  );
}

function ResetPasswordContent() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token");

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (!token) {
      setError("This reset link is missing its token — use the link from your email directly.");
      return;
    }
    if (newPassword.length < 8) {
      setError("Password needs to be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }

    setLoading(true);
    try {
      await api("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      setDone(true);
      clearToken();
      setTimeout(() => router.push("/login"), 2500);
    } catch (err: any) {
      setError(err.message || "This reset link is invalid or has expired. Request a new one.");
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <h2>Reset your password</h2>
          <p className="error-text">
            This link is missing its reset token. Make sure you're using
            the link from your email, or request a new one.
          </p>
          <p className="muted" style={{ marginTop: 18, fontSize: "0.88rem" }}>
            <Link href="/forgot-password">Request a new reset link</Link>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <h2>Set a new password</h2>

        {done ? (
          <p>Password updated — redirecting you to log in…</p>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="field">
              <label htmlFor="new-password">New password</label>
              <input id="new-password" type="password" required value={newPassword}
                     onChange={(e) => setNewPassword(e.target.value)} />
              <p className="hint">At least 8 characters.</p>
            </div>
            <div className="field">
              <label htmlFor="confirm-password">Confirm new password</label>
              <input id="confirm-password" type="password" required value={confirmPassword}
                     onChange={(e) => setConfirmPassword(e.target.value)} />
            </div>
            {error && <p className="error-text">{error}</p>}
            <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
              {loading ? "Updating…" : "Update password"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
