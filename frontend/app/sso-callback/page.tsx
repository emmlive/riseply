"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, setToken } from "@/lib/api";

export default function SSOCallbackPage() {
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

    if (!code || !state) {
      setError("Your identity provider didn't return everything needed to complete sign-in — please try again.");
      return;
    }

    // Unlike the Google/Microsoft OAuth callbacks, there's no
    // sessionStorage state check here -- the backend validates state
    // entirely server-side (a single-use, short-lived record tied to
    // the specific organization), since the redirect to the identity
    // provider was itself backend-initiated, not started from a
    // client-side login page that could stash an expected value first.
    api<{ access_token: string }>("/auth/sso/callback", {
      method: "POST",
      body: JSON.stringify({ code, state }),
    })
      .then((res) => {
        setToken(res.access_token);
        router.push("/dashboard");
      })
      .catch((err) => {
        setError(err.message || "Couldn't complete sign-in — please try again.");
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
