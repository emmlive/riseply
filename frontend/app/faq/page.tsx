import Link from "next/link";
import type { Metadata } from "next";
import PublicFooter from "@/components/PublicFooter";
import { FAQS, UPDATED, UPDATED_LABEL } from "@/lib/publicContent";

const URL = "https://riseply.com/faq";

export const metadata: Metadata = {
  title: "Riseply FAQ: pricing, auto-apply, resume honesty, jobs and the extension",
  description:
    "Answers about Riseply: whether it is free, whether it applies for you, where jobs come from, how resume tailoring stays honest, and what the Chrome extension does.",
  alternates: { canonical: URL },
  openGraph: {
    title: "Riseply FAQ", description: "Straight answers about how Riseply works and what it will and won't do.",
    url: URL, siteName: "Riseply", type: "website",
    images: [{ url: "/brand/og.png", width: 1200, height: 630 }],
  },
  twitter: { card: "summary_large_image", images: ["/brand/og.png"] },
};

const JSON_LD = [
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    dateModified: UPDATED,
    mainEntity: FAQS.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
  },
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Riseply", item: "https://riseply.com/" },
      { "@type": "ListItem", position: 2, name: "FAQ", item: URL },
    ],
  },
];

export default function FaqPage() {
  return (
    <div className="auth-shell" style={{ alignItems: "flex-start", paddingTop: 60 }}>
      {JSON_LD.map((d, i) => (
        <script key={i} type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(d) }} />
      ))}
      <main style={{ maxWidth: 680, margin: "0 auto" }}>
        <h1>Riseply FAQ</h1>
        <p className="hint">Last updated {UPDATED_LABEL}</p>
        {FAQS.map((f) => (
          <section key={f.q}>
            <h2 style={{ fontSize: "1.1rem" }}>{f.q}</h2>
            <p>{f.a}</p>
          </section>
        ))}
        <p>
          Still have a question? See <Link href="/how-it-works">how Riseply works</Link> or write to us from the
          Support page after you sign up.
        </p>
        <PublicFooter />
      </main>
    </div>
  );
}
