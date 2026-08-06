import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Buddy as a Service — AI Employee Onboarding Buddy | Riseply",
  description:
    "Digitize your workplace buddy program. Buddy as a Service pairs every new hire with an AI onboarding buddy grounded in your real handbook and culture — private by design, with a real human handoff when it matters. Plans from $199/mo.",
  keywords: [
    "employee onboarding buddy",
    "AI onboarding assistant",
    "new hire buddy program",
    "workplace buddy software",
    "employee onboarding software",
    "buddy as a service",
  ],
  alternates: { canonical: "https://riseply.com/buddy-as-a-service" },
  openGraph: {
    title: "Buddy as a Service — AI Employee Onboarding Buddy",
    description:
      "Every new hire gets an AI onboarding buddy grounded in your real company handbook and culture, with a real human handoff when it matters. Private by design.",
    url: "https://riseply.com/buddy-as-a-service",
    siteName: "Riseply",
    type: "website",
  },
};

const FAQS = [
  {
    q: "What is Buddy as a Service?",
    a: "A company-customized version of Riseply's Job Buddy, built to digitize the traditional workplace practice of assigning new hires a buddy. Your admin uploads real onboarding material — handbook excerpts, culture notes, team and tool info — so every new hire's AI buddy is grounded in your actual company, not generic advice.",
  },
  {
    q: "How is this different from just assigning a human buddy?",
    a: "Human buddy programs are inconsistent by nature — the assigned person is busy with their own job, quality depends entirely on who a new hire happens to get paired with, and most companies have zero visibility into whether it's actually happening. Buddy as a Service gives every employee the same baseline of genuinely useful support, available any time, while still preserving a real human handoff for the things AI structurally can't do — an office tour, a face-to-face introduction.",
  },
  {
    q: "Can managers or HR read employees' conversations?",
    a: "No. Conversation content is private to the employee, always. Admins only ever see aggregate usage — how many employees have joined, how many onboarding plans were generated, average message counts — never what anyone actually said. The one exception is fully employee-initiated: if someone explicitly requests a handoff to a real contact, only the note they personally write gets sent, never their chat history.",
  },
  {
    q: "What does it cost?",
    a: "Starter is $199/month for up to 10 employees. Growth is $599/month for up to 50 employees. Additional seats beyond your plan are $8/seat. Larger organizations can contact us for Enterprise pricing.",
  },
  {
    q: "How do we get our employees set up?",
    a: "Create an organization and you'll get a join code to share with new hires — they enter it once when adding their role. For faster rollout, admins can also upload a CSV roster (exported from Workday or any HRIS) to pre-register expected hires' titles, so employees don't have to type anything in themselves.",
  },
  {
    q: "Does it work if we already use Workday or another HRIS?",
    a: "Yes, via CSV export — works with Workday, BambooHR, ADP, or any system that can export a roster. There's no live API integration with Workday specifically yet; CSV upload gets you most of the practical benefit today without a lengthy IT-mediated integration process.",
  },
];

const SERVICE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Service",
  name: "Buddy as a Service",
  provider: { "@type": "Organization", name: "Riseply", url: "https://riseply.com" },
  description:
    "AI-powered employee onboarding buddy, customized with your company's own materials, for new hires at any stage — just starting, a few months in, or well established.",
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

export default function BuddyAsAServicePage() {
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
        <h1>Buddy as a Service</h1>
        <p className="muted" style={{ fontSize: "1.05rem" }}>
          Every new hire gets an AI onboarding buddy grounded in your real
          handbook and culture — private by design, with a real human
          handoff for the things AI can't do.
        </p>

        <div style={{ display: "flex", gap: 10, margin: "20px 0 32px" }}>
          <Link href="/signup" className="btn btn-primary">Get started</Link>
          <a href="#pricing" className="btn btn-ghost">See pricing</a>
        </div>

        <h2>Why traditional buddy programs fall short</h2>
        <p>
          Most workplace buddy programs fail in predictable ways: the assigned
          person is busy with their own job and treats it as an obligation,
          quality varies wildly depending on who a new hire happens to get
          paired with, and the company usually has zero visibility into
          whether it's even happening — someone could go their entire first
          quarter barely talking to their "buddy" and nobody would know.
        </p>
        <p>
          Buddy as a Service gives every employee the same baseline of
          genuinely thoughtful support — available any time, consistent
          across your whole team, and grounded in your actual company
          materials instead of generic advice.
        </p>

        <h2>How it works</h2>
        <ul>
          <li>
            <strong>Upload your real onboarding material.</strong> Handbook
            excerpts, culture notes, team and tool info — folded into every
            plan and chat reply for your employees.
          </li>
          <li>
            <strong>Plans that match where someone actually is.</strong> A
            first-week checklist and 30/60/90-day plan for a brand-new hire;
            a growth-focused plan instead for someone already established —
            not a one-size-fits-all script.
          </li>
          <li>
            <strong>A real human handoff when it matters.</strong> For things
            AI structurally can't do — an office tour, a face-to-face intro —
            employees can request a real person, with only their own note
            sent, never their chat history.
          </li>
          <li>
            <strong>Fast rollout.</strong> Share a join code, or upload a CSV
            roster exported from Workday or any HRIS to pre-register your
            new hires.
          </li>
        </ul>

        <h2>Private by design</h2>
        <p>
          Admins only ever see aggregate usage — never conversation content.
          This is the same principle behind a real human workplace buddy: the
          company sponsors it, but the conversation stays between the
          employee and their buddy. Read the full breakdown on our{" "}
          <Link href="/security">Security &amp; Trust</Link> page.
        </p>

        <h2 id="pricing">Pricing</h2>
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
