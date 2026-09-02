"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";

// Same CSRF-state pattern as the existing login OAuth callbacks
// (oauth-callback/microsoft, oauth-callback/google) -- state is
// generated server-side (see GET /calendar/connect/microsoft) rather
// than client-side like login's, but verified the same way: stored in
// sessionStorage before the redirect, compared here, discarded either
// way so a stale value can't be replayed.
export default function CalendarCallbackMicrosoftPage() {
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
    const expectedState = sessionStorage.getItem("calendar_oauth_state_microsoft");
    sessionStorage.removeItem("calendar_oauth_state_microsoft");

    if (!code) {
      setError("Microsoft didn't return an authorization code — please try connecting again.");
      return;
    }
    if (!state || state !== expectedState) {
      setError("This request couldn't be verified — please try connecting your calendar again from your profile page.");
      return;
    }

    api("/calendar/callback/microsoft", {
      method: "POST",
      body: JSON.stringify({ code }),
    })
      .then(() => {
        router.push("/dashboard/profile");
      })
      .catch((err) => {
        setError(err.message || "Couldn't finish connecting your calendar — please try again.");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <h2>Connecting your calendar…</h2>
        {error ? (
          <>
            <p className="error-text">{error}</p>
            <p className="muted" style={{ fontSize: "0.88rem" }}>
              <Link href="/dashboard/profile">← Back to your profile</Link>
            </p>
          </>
        ) : (
          <p className="muted">Just a moment.</p>
        )}
      </div>
    </div>
  );
}
