import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Mentor as a Service — AI + Human Mentorship for Growing Teams | Riseply",
  description:
    "Onboarding gets someone started. Mentor as a Service keeps them growing — pair every employee with a real internal mentor, plus an AI growth partner that remembers their goals across every conversation. Included with Riseply for Teams.",
  keywords: [
    "employee mentorship program",
    "workplace mentor matching",
    "AI career mentor",
    "employee retention software",
    "mentorship as a service",
    "career development software",
  ],
  alternates: { canonical: "https://riseply.com/mentor-as-a-service" },
  openGraph: {
    title: "Mentor as a Service — AI + Human Mentorship for Growing Teams",
    description:
      "A real internal mentor, matched 1:1, plus an AI growth partner that remembers what someone's actually working toward. For after onboarding ends, not instead of it.",
    url: "https://riseply.com/mentor-as-a-service",
    siteName: "Riseply",
    type: "website",
  },
};

const FAQS = [
  {
    q: "What is Mentor as a Service?",
    a: "The growth half of the same platform as Buddy as a Service. Where Buddy gets someone through their first weeks, Mentor keeps them growing after that: a real internal mentor matched 1:1 to each employee, plus an AI growth partner in Job Buddy that remembers their stated career goals across every conversation instead of starting fresh each time.",
  },
  {
    q: "Is this a separate purchase from Buddy as a Service?",
    a: "No — same subscription, same account. Buddy and Mentor are two ways of talking about what's included with Riseply for Teams, not two things to buy. If you're already set up with Buddy as a Service, mentor pairing and career goals are already available in your Org Buddy admin panel.",
  },
  {
    q: "Do employees pick their own mentor, or does the company assign one?",
    a: "Admins build a mentor pool from people already at the company — name, email, what they help with, optionally scoped to a specific department — and assign one mentor per employee. An employee sees who their mentor is right in Job Buddy, with a direct way to request an introduction.",
  },
  {
    q: "What does the AI side actually do?",
    a: "Employees can set their own short-term career goals — \"get better at public speaking,\" \"learn Kubernetes,\" whatever it is — directly in Job Buddy. Those goals get folded into every future conversation, so Job Buddy's advice is grounded in what that specific person said they're working toward, the way a real mentor keeps someone's goals in mind over time instead of treating every conversation as a first meeting.",
  },
  {
    q: "Can managers or admins see an employee's career goals?",
    a: "No. Career goals are employee-owned and employee-visible only — the same privacy boundary as the rest of Job Buddy, and deliberately excluded from admin analytics even though checklist and lesson progress aren't. What someone's personally working toward isn't a company metric.",
  },
  {
    q: "Does this replace real management, performance reviews, or 1:1s?",
    a: "No, and it isn't trying to. It's meant to fill the gap most companies actually have: consistent, always-available support between the formal moments — not a replacement for a manager who knows someone's day-to-day work.",
  },
  {
    q: "What does it cost?",
    a: "Included with Riseply for Teams. Starter is $199/month for up to 10 employees, Growth is $599/month for up to 50. Additional seats beyond your plan are $8/seat. Larger organizations can contact us for Enterprise pricing.",
  },
];

const SERVICE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Service",
  name: "Mentor as a Service",
  provider: { "@type": "Organization", name: "Riseply", url: "https://riseply.com" },
  description:
    "AI-powered ongoing career mentorship, paired with real internal 1:1 mentor matching, for employees beyond their first weeks on the job.",
  offers: [
    {
      "@type": "Offer",
      name: "Starter",
      price: "199",
      priceCurrency: "USD",
      description: "Up to 10 employees",
    },
    {
      "@type": "Offer",
      name: "Growth",
      price: "599",
      priceCurrency: "USD",
      description: "Up to 50 employees",
    },
  ],
};

const FAQ_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: FAQS.map((f) => ({
    "@type": "Question",
    name: f.q,
    acceptedAnswer: { "@type": "Answer", text: f.a },
  })),
};

export default function MentorAsAServicePage() {
  return (
    <div className="auth-shell" style={{ alignItems: "flex-start", paddingTop: 60 }}>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(SERVICE_JSON_LD) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(FAQ_JSON_LD) }}
      />
      <div style={{ maxWidth: 680, margin: "0 auto" }}>
        <p className="hint" style={{ marginBottom: 4 }}>FOR TEAMS</p>
        <h1>Mentor as a Service</h1>
        <p className="muted" style={{ fontSize: "1.05rem" }}>
          Onboarding gets someone started. This is what keeps them growing — a real internal
          mentor, matched 1:1, plus an AI growth partner that remembers what someone's actually
          working toward.
        </p>

        <div style={{ display: "flex", gap: 10, margin: "20px 0 32px" }}>
          <Link href="/signup" className="btn btn-primary">Get started</Link>
          <a href="#pricing" className="btn btn-ghost">See pricing</a>
        </div>

        <h2>The gap most companies actually have</h2>
        <p>
          Most onboarding ends around week two, and most employees don't get anything resembling
          real mentorship after that — support becomes whatever their manager has time for, which
          in practice is often not much. The people who'd genuinely benefit from a mentor rarely
          get matched with one deliberately; it happens informally, if it happens at all, and
          entirely depends on who someone happens to sit near.
        </p>
        <p>
          Mentor as a Service makes that deliberate instead of accidental — for every employee,
          not just the ones who happen to click with a manager or find a mentor on their own.
        </p>

        <h2>How it works</h2>
        <ul>
          <li>
            <strong>A real person, matched on purpose.</strong> Build a mentor pool from people
            already at your company, then assign one mentor per employee — company-wide or scoped
            to a specific department. Employees see who their mentor is and can request an
            introduction directly.
          </li>
          <li>
            <strong>An AI growth partner that actually remembers.</strong> Employees set their own
            short-term goals right in Job Buddy — a skill to build, something to get better at —
            and every future conversation is grounded in what they said they're working toward,
            instead of starting over each time.
          </li>
          <li>
            <strong>Fits alongside real management, not around it.</strong> This isn't a
            replacement for a manager who knows someone's actual work — it's consistent support in
            the space between the formal moments, which is exactly where most people fall through
            the cracks today.
          </li>
        </ul>

        <h2>Private by design</h2>
        <p>
          An employee's career goals are theirs — visible only to them, and deliberately excluded
          from admin analytics even though things like onboarding checklist progress aren't. What
          someone's personally working toward isn't a company metric to track. Read the full
          breakdown on our <Link href="/security">Security &amp; Trust</Link> page.
        </p>

        <h2 id="pricing">Pricing</h2>
        <p className="muted" style={{ marginTop: -4 }}>
          Included with Riseply for Teams — not a separate purchase from Buddy as a Service.
        </p>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", margin: "16px 0" }}>
          <div className="card" style={{ flex: "1 1 260px", margin: 0 }}>
            <h3 style={{ marginTop: 0 }}>Starter</h3>
            <p style={{ fontSize: "1.6rem", fontWeight: 700, margin: "4px 0" }}>$199<span className="hint" style={{ fontSize: "0.9rem", fontWeight: 400 }}>/mo</span></p>
            <p className="muted">Up to 10 employees</p>
          </div>
          <div className="card" style={{ flex: "1 1 260px", margin: 0 }}>
            <h3 style={{ marginTop: 0 }}>Growth</h3>
            <p style={{ fontSize: "1.6rem", fontWeight: 700, margin: "4px 0" }}>$599<span className="hint" style={{ fontSize: "0.9rem", fontWeight: 400 }}>/mo</span></p>
            <p className="muted">Up to 50 employees</p>
          </div>
        </div>
        <p className="hint">Additional seats beyond your plan: $8/employee. Larger team? Contact us for Enterprise pricing.</p>

        <h2>Questions</h2>
        {FAQS.map((f) => (
          <div key={f.q} style={{ marginBottom: 18 }}>
            <h3 style={{ fontSize: "1rem", marginBottom: 4 }}>{f.q}</h3>
            <p style={{ margin: 0 }}>{f.a}</p>
          </div>
        ))}

        <div style={{ display: "flex", gap: 10, marginTop: 24 }}>
          <Link href="/signup" className="btn btn-primary">Get started</Link>
        </div>

        <p className="muted" style={{ marginTop: 24, fontSize: "0.9rem" }}>
          Just hired someone? See <Link href="/buddy-as-a-service">Buddy as a Service</Link> for
          getting them through their first weeks.
        </p>

        <p className="muted" style={{ marginTop: 32, fontSize: "0.88rem" }}>
          <Link href="/">← Back home</Link>
        </p>
      </div>
    </div>
  );
}
