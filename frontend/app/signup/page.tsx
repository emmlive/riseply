"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Script from "next/script";
import { api, setToken } from "@/lib/api";
import OAuthButtons from "@/lib/OAuthButtons";

const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || "";

declare global {
  interface Window {
    onTurnstileSuccess?: (token: string) => void;
  }
}

export default function SignupPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [agreeToTerms, setAgreeToTerms] = useState(false);
  const [captchaToken, setCaptchaToken] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    window.onTurnstileSuccess = (token: string) => setCaptchaToken(token);
    return () => { delete window.onTurnstileSuccess; };
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password needs to be at least 8 characters.");
      return;
    }
    if (!agreeToTerms) {
      setError("You'll need to agree to the Terms of Service and Privacy Policy to continue.");
      return;
    }
    if (TURNSTILE_SITE_KEY && !captchaToken) {
      setError("Please complete the verification check below.");
      return;
    }
    setLoading(true);
    try {
      const { access_token } = await api<{ access_token: string }>("/auth/signup", {
        method: "POST",
        body: JSON.stringify({
          email, password, full_name: fullName, agree_to_terms: agreeToTerms,
          captcha_token: captchaToken,
        }),
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
      {TURNSTILE_SITE_KEY && (
        <Script src="https://challenges.cloudflare.com/turnstile/v0/api.js" strategy="afterInteractive" async defer />
      )}
      <div className="auth-card">
        <h2>Create your account</h2>
        <OAuthButtons />
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
          <div className="field" style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
            <input
              id="terms"
              type="checkbox"
              checked={agreeToTerms}
              onChange={(e) => setAgreeToTerms(e.target.checked)}
              style={{ width: "auto", marginTop: 3 }}
            />
            <label htmlFor="terms" style={{ fontWeight: 400, fontSize: "0.85rem", color: "var(--ink)" }}>
              I agree to the <Link href="/terms" target="_blank">Terms of Service</Link> and{" "}
              <Link href="/privacy" target="_blank">Privacy Policy</Link>.
            </label>
          </div>

          {TURNSTILE_SITE_KEY && (
            <div
              className="cf-turnstile"
              data-sitekey={TURNSTILE_SITE_KEY}
              data-callback="onTurnstileSuccess"
              style={{ marginBottom: 16 }}
            />
          )}

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
