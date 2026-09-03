import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Riseply Enterprise — Onboarding, Mentorship & Internal Mobility for Teams",
  description:
    "Riseply Enterprise is one platform covering an employee's whole arc at your company: Buddy as a Service for onboarding, Mentor as a Service for ongoing growth, and Internal Jobs for internal mobility. Plans from $199/mo.",
  keywords: [
    "riseply enterprise",
    "employee onboarding software",
    "employee mentorship program",
    "internal mobility software",
    "employee retention software",
    "HR software for growing teams",
  ],
  alternates: { canonical: "https://riseply.com/riseply-enterprise" },
  openGraph: {
    title: "Riseply Enterprise — Onboarding, Mentorship & Internal Mobility for Teams",
    description:
      "One platform, an employee's whole arc: onboarding, ongoing mentorship, and internal mobility — not three separate tools to stitch together.",
    url: "https://riseply.com/riseply-enterprise",
    siteName: "Riseply",
    type: "website",
  },
};

const PILLARS = [
  {
    name: "Buddy as a Service",
    href: "/buddy-as-a-service",
    tag: "Onboarding",
    desc: "Every new hire gets an AI onboarding buddy grounded in your real handbook and culture — private by design, with a real human handoff for the things AI can't do.",
  },
  {
    name: "Mentor as a Service",
    href: "/mentor-as-a-service",
    tag: "Growth",
    desc: "A real internal mentor, matched 1:1 or as a group, plus an AI growth partner that remembers what someone's actually working toward — for after onboarding ends.",
  },
  {
    name: "Internal Jobs",
    href: "/internal-jobs",
    tag: "Mobility",
    desc: "Post open roles at your own company and let employees apply with the resume already on file — keeping good people growing here instead of leaving for a job board.",
  },
];

const FAQS = [
  {
    q: "What is Riseply Enterprise?",
    a: "The umbrella name for Riseply's whole B2B platform — Buddy as a Service, Mentor as a Service, and Internal Jobs, all in one subscription, one account, one admin panel. It's built to cover an employee's whole arc at your company: getting started, growing, and eventually moving into a new role internally instead of leaving.",
  },
  {
    q: "Do I have to buy all three, or can I use just one?",
    a: "One subscription includes all three — there's no separate purchase per pillar. Most teams start with Buddy as a Service for onboarding and grow into using Mentor and Internal Jobs as their team matures, but everything is available from day one.",
  },
  {
    q: "How is this different from Riseply's individual job-search product?",
    a: "Completely separate audiences and, largely, separate systems. Riseply's core product helps an individual find and apply to jobs at OTHER companies. Riseply Enterprise is what a company itself uses to onboard, mentor, and internally move its own employees — the two share some underlying AI infrastructure, but they're built for different people solving different problems.",
  },
  {
    q: "Can managers or admins see employee conversations?",
    a: "No. Conversation content, meeting notes, and career goals all stay private to the employee across every pillar — Buddy, Mentor, and Internal Jobs alike. Admins only ever see aggregate program-health numbers, never what anyone actually said. Read the full breakdown on our Security & Trust page.",
  },
  {
    q: "What does it cost?",
    a: "Starter is $199/month for up to 10 employees, Growth is $599/month for up to 50 — both include all three pillars. Additional seats beyond your plan are $8/seat. Larger organizations can contact us for Enterprise pricing.",
  },
  {
    q: "How do we get started?",
    a: "Create an organization and you'll get a join code to share with employees — they enter it once. For faster rollout, upload a CSV roster exported from Workday or any HRIS to pre-register expected hires' titles.",
  },
];

const SERVICE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Service",
  name: "Riseply Enterprise",
  provider: { "@type": "Organization", name: "Riseply", url: "https://riseply.com" },
  description:
    "One platform covering an employee's whole arc: AI-powered onboarding, ongoing mentorship, and internal mobility for growing teams.",
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

export default function RiseplyEnterprisePage() {
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
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <p className="hint" style={{ marginBottom: 4 }}>FOR TEAMS</p>
        <h1>Riseply Enterprise</h1>
        <p className="muted" style={{ fontSize: "1.05rem" }}>
          One platform for an employee's whole arc at your company — getting started, growing,
          and moving into what's next, all without leaving for somewhere else.
        </p>

        <div style={{ display: "flex", gap: 10, margin: "20px 0 32px" }}>
          <Link href="/signup" className="btn btn-primary">Get started</Link>
          <a href="#pricing" className="btn btn-ghost">See pricing</a>
        </div>

        <h2>Three pillars, one subscription</h2>
        <p>
          Most companies stitch together separate tools for onboarding, mentorship, and internal
          mobility — if they have any of the three at all. Riseply Enterprise covers all three in
          one platform, one admin panel, one place employees already go for everything else.
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 16, margin: "20px 0 32px" }}>
          {PILLARS.map((p) => (
            <Link
              key={p.href}
              href={p.href}
              className="card"
              style={{ textDecoration: "none", color: "inherit", display: "block", margin: 0 }}
            >
              <p className="hint" style={{ marginBottom: 2 }}>{p.tag.toUpperCase()}</p>
              <h3 style={{ marginTop: 0, marginBottom: 6 }}>{p.name} →</h3>
              <p style={{ margin: 0 }}>{p.desc}</p>
            </Link>
          ))}
        </div>

        <h2>Private by design, across all three</h2>
        <p>
          Conversation content, meeting notes, and career goals stay private to the employee —
          the same privacy boundary whether they're chatting with their onboarding buddy, meeting
          with a mentor, or applying to an internal opening. Admins only ever see aggregate
          program-health numbers, never the actual words exchanged. Read the full breakdown on
          our <Link href="/security">Security &amp; Trust</Link> page.
        </p>

        <h2 id="pricing">Pricing</h2>
        <p className="muted" style={{ marginTop: -4 }}>
          One subscription includes all three pillars — nothing sold separately.
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

        <p className="muted" style={{ marginTop: 32, fontSize: "0.88rem" }}>
          <Link href="/">← Back home</Link>
        </p>
      </div>
    </div>
  );
}
