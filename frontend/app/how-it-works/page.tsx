import Link from "next/link";
import type { Metadata } from "next";
import PublicFooter from "@/components/PublicFooter";
import { STAGES, UPDATED, UPDATED_LABEL } from "@/lib/publicContent";

const URL = "https://riseply.com/how-it-works";

export const metadata: Metadata = {
  title: "How Riseply works: AI job matching, resume tailoring and interview prep",
  description:
    "Riseply matches new jobs to your resume every day, tailors an ATS-friendly resume for each one without inventing experience, helps fill in applications, and coaches you through interviews and your next role. You approve every step.",
  alternates: { canonical: URL },
  openGraph: {
    title: "How Riseply works",
    description: "Get ready, find, apply, win, grow: five stages, with you approving every step.",
    url: URL, siteName: "Riseply", type: "article",
    images: [{ url: "/brand/og.png", width: 1200, height: 630 }],
  },
  twitter: { card: "summary_large_image", images: ["/brand/og.png"] },
};

const JSON_LD = [
  {
    "@context": "https://schema.org",
    "@type": "HowTo",
    name: "How Riseply takes you from job search to your next role",
    description: "Riseply works in five stages: get ready, find, apply, win and grow.",
    step: STAGES.map((s, i) => ({ "@type": "HowToStep", position: i + 1, name: s.name, text: `${s.summary} ${s.what.join(" ")}` })),
  },
  {
    "@context": "https://schema.org",
    "@type": "WebPage",
    name: "How Riseply works",
    url: URL,
    dateModified: UPDATED,
    isPartOf: { "@type": "WebSite", name: "Riseply", url: "https://riseply.com" },
  },
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Riseply", item: "https://riseply.com/" },
      { "@type": "ListItem", position: 2, name: "How it works", item: URL },
    ],
  },
];

export default function HowItWorksPage() {
  return (
    <div className="auth-shell" style={{ alignItems: "flex-start", paddingTop: 60 }}>
      {JSON_LD.map((d, i) => (
        <script key={i} type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(d) }} />
      ))}
      <main style={{ maxWidth: 680, margin: "0 auto" }}>
        <h1>How Riseply works</h1>
        <p style={{ fontSize: "1.05rem" }}>
          Riseply is an AI job-search platform that matches new jobs to your resume every day, writes a tailored
          resume for each one using only what is already in yours, and helps you apply, interview and grow into the
          next role. You approve every step, and nothing is sent to an employer without your OK.
        </p>
        <p className="hint">Last updated {UPDATED_LABEL}</p>

        <p>It works in five stages. Each one hands the next what it needs, so you never start from a blank page.</p>

        {STAGES.map((s, i) => (
          <section key={s.name}>
            <h2>{i + 1}. {s.name}</h2>
            <p><strong>{s.summary}</strong></p>
            <ul>{s.what.map((w) => <li key={w}>{w}</li>)}</ul>
          </section>
        ))}

        <h2>The rules Riseply follows</h2>
        <ul>
          <li><strong>You decide.</strong> Riseply prepares and suggests. It does not submit applications or send messages on its own.</li>
          <li><strong>Nothing invented.</strong> Resumes, cover letters and answers are built from your own resume and profile. A skill you do not have is not added.</li>
          <li><strong>Blank means skip.</strong> Autofill only fills answers you chose yourself and lists everything it left for you.</li>
          <li><strong>Your logins stay with you.</strong> Job-site usernames and passwords you save in the extension stay in your browser.</li>
        </ul>

        <h2>Who it is for</h2>
        <p>
          Anyone searching for a job, changing careers, or preparing for a certification exam. Teams can use the same
          approach through <Link href="/riseply-enterprise">Riseply Enterprise</Link>: onboarding buddies, mentoring
          and internal mobility.
        </p>

        <div style={{ display: "flex", gap: 10, margin: "24px 0" }}>
          <Link href="/signup" className="btn btn-primary">Get started free</Link>
          <Link href="/faq" className="btn btn-ghost">Read the FAQ</Link>
        </div>
        <PublicFooter />
      </main>
    </div>
  );
}
