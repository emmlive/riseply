"use client";

import Link from "next/link";

export default function PrivacyPage() {
  return (
    <div className="auth-shell" style={{ alignItems: "flex-start", paddingTop: 60 }}>
      <div style={{ maxWidth: 680, margin: "0 auto" }}>
        <h1>Privacy Policy</h1>
        <p className="muted">Last updated: August 2026</p>

        <p><em>
          This is a starting template, not a substitute for legal advice —
          particularly around GDPR, CCPA, or other regional privacy law
          compliance if you have users in those jurisdictions. Have a
          lawyer review this before relying on it for a real product.
        </em></p>

        <h2>What we collect</h2>
        <p>
          Your account email and password (stored as a hash, never in
          plain text), your resume text, search profile preferences, and
          the applications, interview prep, onboarding plans, and Job
          Buddy conversations generated through your use of the app.
        </p>

        <h2>How it's used</h2>
        <p>
          Your resume and job details are sent to Anthropic's Claude API
          to score matches, tailor resumes, and generate interview and
          onboarding content. Anthropic's own API terms govern how they
          handle that data in processing your request. We don't sell your
          personal data to third parties.
        </p>

        <h2>Email notifications</h2>
        <p>
          If email notifications are configured, we send you match
          alerts and generated documents via the email address on your
          account.
        </p>

        <h2>Payments</h2>
        <p>
          If you choose to leave a tip, payment is processed by Stripe.
          We don't store your card details — Stripe handles that
          directly.
        </p>

        <h2>Data retention and deletion</h2>
        <p>
          Your data is retained as long as your account is active.
          Contact us if you'd like your account and associated data
          deleted.
        </p>

        <h2>Job Buddy conversations</h2>
        <p>
          Messages you send to Job Buddy are stored so the conversation
          has continuity, and are visible only to you. They're used to
          generate responses via the Claude API and aren't used for any
          purpose beyond providing the feature to you.
        </p>

        <p style={{ marginTop: 32 }}>
          See also our <Link href="/terms">Terms of Service</Link>.
        </p>
      </div>
    </div>
  );
}
