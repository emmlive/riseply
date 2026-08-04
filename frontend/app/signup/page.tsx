"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, setToken } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password needs to be at least 8 characters.");
      return;
    }
    setLoading(true);
    try {
      const { access_token } = await api<{ access_token: string }>("/auth/signup", {
        method: "POST",
        body: JSON.stringify({ email, password, full_name: fullName }),
      });
      setToken(access_token);
      router.push("/dashboard");
    } catch (err: any) {
      setError(err.message || "Couldn't create your account.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <h2>Create your account</h2>
        <form onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="name">Full name</label>
            <input id="name" required value={fullName}
                   onChange={(e) => setFullName(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input id="email" type="email" required value={email}
                   onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input id="password" type="password" required value={password}
                   onChange={(e) => setPassword(e.target.value)} />
            <p className="hint">At least 8 characters.</p>
          </div>
          {error && <p className="error-text">{error}</p>}
          <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
            {loading ? "Creating account…" : "Create account"}
          </button>
        </form>
        <p className="muted" style={{ marginTop: 18, fontSize: "0.88rem" }}>
          Already have an account? <Link href="/login">Log in</Link>
        </p>
      </div>
    </div>
  );
}
