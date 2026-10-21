import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy — Riseply",
  description: "How Riseply collects, uses, and protects your data — job search info, resume content, and Job Buddy conversations.",
  alternates: { canonical: "https://riseply.com/privacy" },
};

export default function PrivacyPage() {
  return (
    <div className="auth-shell" style={{ alignItems: "flex-start", paddingTop: 60 }}>
      <div style={{ maxWidth: 680, margin: "0 auto" }}>
        <h1>Privacy Policy</h1>
        <p className="muted">Last updated: October 2026</p>

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

        <h2>Riseply Autofill browser extension</h2>
        <p>
          The Riseply Autofill extension for Chrome runs on web pages so it can
          recognise job postings and application forms. Recognising a page
          happens inside your browser and nothing is sent anywhere. The
          extension sends data to Riseply only when you click a button in its
          sidebar:
        </p>
        <ul>
          <li>
            <strong>Score my resume</strong>, <strong>Generate cover letter</strong> and
            <strong> suggested answers</strong> send the text of the job posting
            you are viewing, and the question you asked about, to Riseply so
            your resume can be compared with it. Your resume is already stored
            in your account.
          </li>
          <li>
            <strong>Autofill this page</strong> fetches your saved name, email,
            phone, location and profile links from your account and types them
            into the form on the page. It does not submit the form.
          </li>
        </ul>
        <p>
          The extension stores one thing in your browser: a sign-in token, so
          you stay logged in. Logging out removes it. We do not sell this data,
          use it for advertising, or use it for anything other than the feature
          you clicked. We do not read or keep your browsing history.
        </p>

        <h2>Job Buddy conversations</h2>
        <p>
          Messages you send to Job Buddy are stored so the conversation
          has continuity, and are visible only to you. They're used to
          generate responses via the Claude API and aren't used for any
          purpose beyond providing the feature to you.
        </p>

        <h2>Career Coach notes</h2>
        <p>
          After a learning session, the Career Coach saves a few short notes
          about how you learn (what clicked, what is still shaky, one piece of
          homework) so the next session can pick up where you stopped. The
          notes are visible only to you under <strong>What your coach
          remembers</strong> on the Career Coach page, where you can delete any
          note, clear them all, or turn remembering off. We tell the coach not
          to save personal details, and interview and negotiation role-plays
          never use the notes.
        </p>

        <p style={{ marginTop: 32 }}>
          See also our <Link href="/terms">Terms of Service</Link>.
        </p>
      </div>
    </div>
  );
}
