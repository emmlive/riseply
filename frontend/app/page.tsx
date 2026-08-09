import Link from "next/link";
import type { Metadata } from "next";
import RedirectIfLoggedIn from "@/components/RedirectIfLoggedIn";

export const metadata: Metadata = {
  title: "Riseply — AI job search, resume tailoring, and employee onboarding",
  description: "Riseply finds jobs that fit, tailors your resume for each one, preps you for interviews, and helps you onboard once you land the offer. Also powers Buddy as a Service — a company-customized AI onboarding buddy for new hires.",
  alternates: { canonical: "https://riseply.com/" },
  openGraph: {
    title: "Riseply — AI job search & employee onboarding",
    description: "Find roles that fit, tailor your resume per job, and get an AI onboarding buddy once you land it — with live response-rate data from everyone using it.",
    url: "https://riseply.com/",
    siteName: "Riseply",
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "Riseply — AI job search & employee onboarding",
    description: "Find roles that fit, tailor your resume per job, and get an AI onboarding buddy once you land it.",
  },
};

const FEATURES = [
  { label: "Find", desc: "Matches roles to your resume, scored by AI" },
  { label: "Tailor", desc: "Rewrites your resume per job — nothing invented" },
  { label: "Prep", desc: "Interview questions and an onboarding plan" },
  { label: "Rise", desc: "Live response-rate data from everyone using it" },
];

const ORG_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "Riseply",
  url: "https://riseply.com",
  logo: "https://riseply.com/brand/icon.svg",
  description: "AI-powered job search platform: job matching, resume tailoring, interview prep, and employee onboarding, including Buddy as a Service for companies.",
};

export default function HomePage() {
  return (
    <div className="auth-shell">
      <RedirectIfLoggedIn />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(ORG_JSON_LD) }}
      />
      <div style={{ textAlign: "center", maxWidth: 560 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, marginBottom: 4 }}>
          <img src="/brand/icon.svg" alt="" width={40} height={40} />
          <h1 style={{ fontStyle: "italic", margin: 0 }}>Riseply</h1>
        </div>
        <p className="muted" style={{ marginBottom: 8 }}>
          Riseply finds roles that fit, tailors your resume for each one,
          preps you for interviews, and helps you settle into your first
          weeks once you land it — all while you stay in control. Nothing
          goes out without your OK.
        </p>

        <div style={{
          display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 12,
          margin: "24px 0", textAlign: "left",
        }}>
          {FEATURES.map((f) => (
            <div key={f.label} style={{
              background: "var(--surface)", border: "1px solid var(--border)",
              borderRadius: 10, padding: "12px 14px",
            }}>
              <div style={{ fontFamily: "var(--font-display)", fontStyle: "italic", fontSize: "0.95rem", marginBottom: 4 }}>
                {f.label}
              </div>
              <div className="hint" style={{ lineHeight: 1.4 }}>{f.desc}</div>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
          <Link href="/login" className="btn btn-ghost">Log in</Link>
          <Link href="/signup" className="btn btn-primary">Get started</Link>
        </div>
        <p className="muted" style={{ marginTop: 20, fontSize: "0.85rem" }}>
          Hiring? See <Link href="/buddy-as-a-service">Buddy as a Service</Link> for your team's onboarding.
        </p>
        <p className="muted" style={{ marginTop: 8, fontSize: "0.8rem" }}>
          <Link href="/terms">Terms of Service</Link> · <Link href="/privacy">Privacy Policy</Link> · <Link href="/security">Security & Trust</Link>
        </p>
      </div>
    </div>
  );
}
