import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Security & Trust — Riseply",
  description: "How Riseply secures your account and protects your privacy — bcrypt password hashing, private Job Buddy conversations, anonymized Rise Index data, and more, explained specifically.",
  alternates: { canonical: "https://riseply.com/security" },
};

export default function SecurityPage() {
  return (
    <div className="auth-shell" style={{ alignItems: "flex-start", paddingTop: 60 }}>
      <div style={{ maxWidth: 680, margin: "0 auto" }}>
        <h1>Security &amp; Trust</h1>
        <p className="muted">
          Specifics, not just reassurances — here's exactly how Riseply
          handles your account, your data, and your privacy.
        </p>

        <h2>Account security</h2>
        <ul>
          <li>Passwords are hashed with bcrypt — never stored, logged, or visible to us in plain text.</li>
          <li>
            Password resets use a single-use, time-limited link (30 minutes) — the token itself is
            hashed before storage, the same principle as your password, so a database leak alone
            couldn't be used to reset anyone's account.
          </li>
          <li>Resetting your password immediately signs you out of every other active session, as a safety measure.</li>
          <li>
            The "forgot password" flow never reveals whether a given email has an account —
            it returns the same response either way, so it can't be used to check who's on Riseply.
          </li>
          <li>Signup, login, and password-reset requests are rate-limited per IP address to deter brute-force and abuse.</li>
          <li>Optional CAPTCHA (Cloudflare Turnstile) is available as an added layer against automated signup abuse.</li>
        </ul>

        <h2>Your Job Buddy conversations are private</h2>
        <p>
          If your employer has set up "Org Buddy" for your company, their admin can only ever see
          <strong> aggregate usage</strong> — how many employees have joined, how many onboarding
          plans were generated, average message counts. They cannot see the content of what you've
          said, ever. This is the same design principle behind a real human workplace buddy: the
          company sponsors it, but the conversation stays between you and your buddy.
        </p>
        <p>
          The one deliberate exception: if you explicitly choose to "Request a handoff" to connect
          with a real person at your company (for something like an office tour), only the note you
          personally write gets sent to them — never your chat history, and never an AI-generated
          summary of it. You control exactly what leaves your conversation, in your own words.
        </p>

        <h2>AI safety</h2>
        <ul>
          <li>
            Job postings come from external job boards and ATS feeds — untrusted content by nature.
            Every feature that sends a posting to Claude treats it strictly as data to analyze, never
            as instructions to follow, specifically to defend against prompt-injection attempts
            hidden inside a posting.
          </li>
          <li>
            Job Buddy is scoped to career and workplace topics, and is not a substitute for a lawyer,
            doctor, or accountant. If you describe harassment, discrimination, or a safety concern,
            it's built to take that seriously and point you to HR, an employment lawyer, or the
            relevant authority — not try to resolve it itself.
          </li>
          <li>
            The Knowledge Base assistant only ever answers from real, written help articles. If
            nothing in our documentation actually covers your question, it says so plainly rather
            than guessing — a wrong guess about pricing or privacy would be actively misleading, not
            just unhelpful.
          </li>
        </ul>

        <h2>Auto-submit guardrails</h2>
        <p>
          Auto-submit is off by default. Even when a company enables it, it only ever acts on an
          application <em>you've</em> already reviewed and approved, and only on a specific allowlist
          of legitimate hiring platforms (Greenhouse, Lever, Ashby, Workable). LinkedIn and Indeed are
          explicitly and permanently blocked in code, not just left off a list.
        </p>

        <h2>Anonymized, not identifiable</h2>
        <p>
          The Rise Index shows live response-rate data (e.g. "68% of applicants heard back from Acme
          Corp") pulled from everyone using Riseply — but a company's stats only become visible once
          enough people have applied there, specifically to keep individual applicants from being
          identifiable in a small sample.
        </p>

        <h2>Payments</h2>
        <p>
          All payment processing is handled by Stripe. Riseply never sees or stores your raw card
          number — Stripe handles that directly.
        </p>

        <h2>Infrastructure</h2>
        <p>
          All traffic to Riseply is encrypted in transit (HTTPS/TLS). We don't sell your personal
          data to third parties.
        </p>

        <h2>What we're still working on</h2>
        <p>
          We'd rather tell you this plainly than have you find out the hard way:
        </p>
        <ul>
          <li>
            Our <Link href="/terms">Terms of Service</Link> and <Link href="/privacy">Privacy Policy</Link> are
            starting templates, still undergoing full legal review — not yet a substitute for
            professional legal advice.
          </li>
          <li>
            We don't currently verify email addresses at signup (only password reset, which does
            verify via a real emailed link).
          </li>
          <li>
            We don't hold formal security certifications (like SOC 2) at this stage — we're a
            growing product, and we'd rather be upfront about that than imply otherwise.
          </li>
        </ul>
        <p>
          Found a security concern? Please reach out through the <Link href="/login">Support tab</Link> in
          your dashboard and a person will follow up.
        </p>

        <p className="muted" style={{ marginTop: 32, fontSize: "0.88rem" }}>
          <Link href="/">← Back home</Link>
        </p>
      </div>
    </div>
  );
}
