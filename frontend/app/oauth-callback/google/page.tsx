"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, setToken } from "@/lib/api";

export default function GoogleOAuthCallbackPage() {
  return (
    <Suspense fallback={null}>
      <Callback />
    </Suspense>
  );
}

function Callback() {
  const params = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState("");

  useEffect(() => {
    const code = params.get("code");
    const state = params.get("state");
    const expectedState = sessionStorage.getItem("oauth_state_google");
    sessionStorage.removeItem("oauth_state_google");

    if (!code) {
      setError("Google didn't return an authorization code — please try again.");
      return;
    }
    if (!state || state !== expectedState) {
      setError("This sign-in request couldn't be verified — please try again from the login page.");
      return;
    }

    api<{ access_token: string }>("/auth/oauth/google/callback", {
      method: "POST",
      body: JSON.stringify({ code }),
    })
      .then((res) => {
        setToken(res.access_token);
        router.push("/dashboard");
      })
      .catch((err) => {
        setError(err.message || "Couldn't complete Google sign-in — please try again.");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <h2>Signing you in…</h2>
        {error ? (
          <>
            <p className="error-text">{error}</p>
            <p className="muted" style={{ fontSize: "0.88rem" }}>
              <Link href="/login">← Back to log in</Link>
            </p>
          </>
        ) : (
          <p className="muted">Just a moment.</p>
        )}
      </div>
    </div>
  );
}
