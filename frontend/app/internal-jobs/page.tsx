import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Internal Jobs — Internal Mobility Software for Growing Teams | Riseply",
  description:
    "Keep good people growing at your company instead of losing them to a job board. Internal Jobs lets you post open roles at your own organization and employees apply with the resume already on file, right from Job Buddy. Included with Riseply for Teams.",
  keywords: [
    "internal mobility software",
    "internal job board",
    "employee retention software",
    "internal hiring platform",
    "internal transfer software",
    "talent mobility",
  ],
  alternates: { canonical: "https://riseply.com/internal-jobs" },
  openGraph: {
    title: "Internal Jobs — Internal Mobility Software for Growing Teams",
    description:
      "Post open roles at your own company and let employees apply with the resume already on file — no external search, no fresh upload.",
    url: "https://riseply.com/internal-jobs",
    siteName: "Riseply",
    type: "website",
  },
};

const FAQS = [
  {
    q: "What is Internal Jobs?",
    a: "A way for your own organization to post open roles internally, and for employees to discover and apply to them without ever leaving Job Buddy. It's the third pillar of Riseply Enterprise, alongside Buddy as a Service (onboarding) and Mentor as a Service (ongoing growth) — the same platform, covering what happens when someone's ready to move into a different role at your company instead of leaving for one somewhere else.",
  },
  {
    q: "Is this a separate purchase from Buddy or Mentor as a Service?",
    a: "No — same subscription, same account, included with Riseply for Teams. If you're already set up with Org Buddy, Internal Jobs is already available in your admin panel.",
  },
  {
    q: "How is this different from Riseply's regular job matching?",
    a: "Completely separate systems. Riseply's core product discovers EXTERNAL jobs from other companies for individual job seekers, scored by AI against a resume. Internal Jobs is admin-authored and org-scoped from the start — you post the opening, it's only ever visible to your own employees, and there's no AI matching involved. It exists specifically so an employee's \"find my next role\" instinct points inward, at your own openings, instead of outward at a job board.",
  },
  {
    q: "Do employees need to upload a new resume to apply?",
    a: "No. Applying internally uses the resume already on file — no fresh upload, no tailoring for an external company's ATS. Whoever reviews an internal application already has more context on that person than an external resume alone would give them anyway.",
  },
  {
    q: "Can employees see postings from other departments?",
    a: "Yes, by default — internal postings are visible company-wide, not siloed to one department, so someone in Support can see and apply to an opening in Engineering. Admins choose whether to tag a posting to a specific department for organizational clarity, but that's informational, not a visibility restriction.",
  },
  {
    q: "What happens after someone applies?",
    a: "The admin who manages Internal Jobs sees every applicant for a posting — name, email, and their note — and can close a posting once it's filled. There's no automated screening or ranking; a real person reviews real applicants, the same way any internal transfer conversation would normally start.",
  },
  {
    q: "What does it cost?",
    a: "Included with Riseply for Teams. Starter is $199/month for up to 10 employees, Growth is $599/month for up to 50. Additional seats beyond your plan are $8/seat. Larger organizations can contact us for Enterprise pricing.",
  },
];

const SERVICE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Service",
  name: "Internal Jobs",
  provider: { "@type": "Organization", name: "Riseply", url: "https://riseply.com" },
  description:
    "Internal mobility software — post open roles at your own organization and let employees apply with the resume already on file, right from Job Buddy.",
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

export default function InternalJobsPage() {
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
        <h1>Internal Jobs</h1>
        <p className="muted" style={{ fontSize: "1.05rem" }}>
          Keep good people growing at your company instead of losing them to a job board — post
          open roles internally, and employees apply with the resume already on file, right from
          Job Buddy.
        </p>

        <div style={{ display: "flex", gap: 10, margin: "20px 0 32px" }}>
          <Link href="/signup" className="btn btn-primary">Get started</Link>
          <a href="#pricing" className="btn btn-ghost">See pricing</a>
        </div>

        <h2>The retention gap most companies don't notice until it's too late</h2>
        <p>
          Someone ready for their next challenge doesn't always need a new employer — they often
          just need a next role. But without a real, visible way to discover what's open
          internally, the path of least resistance is checking a job board instead, and by the
          time an employer finds out someone's looking, they're usually already gone.
        </p>
        <p>
          Internal Jobs makes internal openings as easy to discover as external ones — right where
          an employee already spends time in Job Buddy, not buried in an email or a Slack channel
          only some people happen to see.
        </p>

        <h2>How it works</h2>
        <ul>
          <li>
            <strong>Post an opening in minutes.</strong> Title, an optional department, a
            description — no external job board listing, no separate ATS to configure.
          </li>
          <li>
            <strong>Employees apply with what's already on file.</strong> The resume they already
            have in Riseply, plus an optional note — no fresh upload, no external tailoring.
          </li>
          <li>
            <strong>Visible company-wide by default.</strong> Someone in one department can see
            and apply to an opening in another — internal mobility works best when it isn't
            siloed.
          </li>
          <li>
            <strong>A real person reviews every applicant.</strong> No automated ranking or
            screening — just a clear list of who applied and what they said, the same way any real
            internal transfer conversation starts.
          </li>
        </ul>

        <h2>The third pillar</h2>
        <p>
          Internal Jobs is part of Riseply Enterprise, alongside{" "}
          <Link href="/buddy-as-a-service">Buddy as a Service</Link> (getting someone through
          their first weeks) and <Link href="/mentor-as-a-service">Mentor as a Service</Link>{" "}
          (ongoing growth once onboarding wraps up). Together, they cover an employee's whole
          arc at your company — not just the beginning.
        </p>

        <h2 id="pricing">Pricing</h2>
        <p className="muted" style={{ marginTop: -4 }}>
          Included with Riseply for Teams — not a separate purchase from Buddy or Mentor as a
          Service.
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
          See the full picture at <Link href="/riseply-enterprise">Riseply Enterprise</Link>.
        </p>

        <p className="muted" style={{ marginTop: 32, fontSize: "0.88rem" }}>
          <Link href="/">← Back home</Link>
        </p>
      </div>
    </div>
  );
}
