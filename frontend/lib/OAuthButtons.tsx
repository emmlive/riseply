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

function GoogleLogo() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" style={{ flexShrink: 0 }}>
      <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/>
      <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"/>
      <path fill="#FBBC05" d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.348 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z"/>
      <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/>
    </svg>
  );
}

function MicrosoftLogo() {
  return (
    <svg width="18" height="18" viewBox="0 0 21 21" style={{ flexShrink: 0 }}>
      <rect x="1" y="1" width="9" height="9" fill="#f25022"/>
      <rect x="11" y="1" width="9" height="9" fill="#7fba00"/>
      <rect x="1" y="11" width="9" height="9" fill="#00a4ef"/>
      <rect x="11" y="11" width="9" height="9" fill="#ffb900"/>
    </svg>
  );
}

export default function OAuthButtons() {
  if (!GOOGLE_CLIENT_ID && !MICROSOFT_CLIENT_ID) return null;

  return (
    <div style={{ marginBottom: 18 }}>
      <div style={{ display: "flex", gap: 8, flexDirection: "column" }}>
        {GOOGLE_CLIENT_ID && (
          <button type="button" className="btn btn-ghost btn-block" onClick={redirectToGoogle}
                  style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10 }}>
            <GoogleLogo />
            Continue with Google
          </button>
        )}
        {MICROSOFT_CLIENT_ID && (
          <button type="button" className="btn btn-ghost btn-block" onClick={redirectToMicrosoft}
                  style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10 }}>
            <MicrosoftLogo />
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
