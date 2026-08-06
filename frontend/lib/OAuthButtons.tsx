"use client";

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";
const MICROSOFT_CLIENT_ID = process.env.NEXT_PUBLIC_MICROSOFT_CLIENT_ID || "";

function randomState(): string {
  // crypto.randomUUID() is available in every browser this app targets
  return crypto.randomUUID();
}

function redirectToGoogle() {
  const state = randomState();
  sessionStorage.setItem("oauth_state_google", state);
  const redirectUri = `${window.location.origin}/oauth-callback/google`;
  const url = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  url.searchParams.set("client_id", GOOGLE_CLIENT_ID);
  url.searchParams.set("redirect_uri", redirectUri);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", "openid email profile");
  url.searchParams.set("state", state);
  url.searchParams.set("access_type", "online");
  url.searchParams.set("prompt", "select_account");
  window.location.href = url.toString();
}

function redirectToMicrosoft() {
  const state = randomState();
  sessionStorage.setItem("oauth_state_microsoft", state);
  const redirectUri = `${window.location.origin}/oauth-callback/microsoft`;
  const url = new URL("https://login.microsoftonline.com/common/oauth2/v2.0/authorize");
  url.searchParams.set("client_id", MICROSOFT_CLIENT_ID);
  url.searchParams.set("redirect_uri", redirectUri);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", "openid email profile User.Read");
  url.searchParams.set("state", state);
  url.searchParams.set("response_mode", "query");
  window.location.href = url.toString();
}

export default function OAuthButtons() {
  if (!GOOGLE_CLIENT_ID && !MICROSOFT_CLIENT_ID) return null;

  return (
    <div style={{ marginBottom: 18 }}>
      <div style={{ display: "flex", gap: 8, flexDirection: "column" }}>
        {GOOGLE_CLIENT_ID && (
          <button type="button" className="btn btn-ghost btn-block" onClick={redirectToGoogle}>
            Continue with Google
          </button>
        )}
        {MICROSOFT_CLIENT_ID && (
          <button type="button" className="btn btn-ghost btn-block" onClick={redirectToMicrosoft}>
            Continue with Microsoft
          </button>
        )}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "18px 0" }}>
        <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
        <span className="hint">or</span>
        <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
      </div>
    </div>
  );
}
