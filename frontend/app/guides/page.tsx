import Link from "next/link";
import type { Metadata } from "next";
import PublicFooter from "@/components/PublicFooter";
import { GUIDES, GUIDES_PUBLISHED } from "@/lib/guides";

const URL = "https://riseply.com/guides";

export const metadata: Metadata = {
  title: "Job search guides: resumes, ATS, applications, interviews and exams | Riseply",
  description: "Plain answers to common job-search questions: tailoring a resume honestly, ATS-friendly formatting, filling in applications safely, following up, interviews and certification study plans.",
  alternates: { canonical: URL },
  openGraph: {
    title: "Riseply job search guides", description: "Plain answers to the questions job seekers actually ask.",
    url: URL, siteName: "Riseply", type: "website",
    images: [{ url: "/brand/og.png", width: 1200, height: 630 }],
  },
  twitter: { card: "summary_large_image", images: ["/brand/og.png"] },
};

const JSON_LD = [
  {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: "Riseply job search guides",
    url: URL,
    dateModified: GUIDES_PUBLISHED,
    hasPart: GUIDES.map((g) => ({ "@type": "Article", headline: g.title, url: `${URL}/${g.slug}` })),
  },
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Riseply", item: "https://riseply.com/" },
      { "@type": "ListItem", position: 2, name: "Guides", item: URL },
    ],
  },
];

export default function GuidesPage() {
  return (
    <div className="auth-shell" style={{ alignItems: "flex-start", paddingTop: 60 }}>
      {JSON_LD.map((d, i) => (
        <script key={i} type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(d) }} />
      ))}
      <main style={{ maxWidth: 680, margin: "0 auto" }}>
        <h1>Job search guides</h1>
        <p style={{ fontSize: "1.05rem" }}>
          Short, practical answers to the questions job seekers ask most. Each guide gives the answer first, then the
          steps.
        </p>
        <ul style={{ paddingLeft: 18 }}>
          {GUIDES.map((g) => (
            <li key={g.slug} style={{ marginBottom: 14 }}>
              <Link href={`/guides/${g.slug}`}><strong>{g.title}</strong></Link>
              <div className="muted" style={{ fontSize: "0.9rem" }}>{g.answer}</div>
            </li>
          ))}
        </ul>
        <PublicFooter />
      </main>
    </div>
  );
}
