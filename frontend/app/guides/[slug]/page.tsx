import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import PublicFooter from "@/components/PublicFooter";
import { GUIDES, GUIDES_PUBLISHED, getGuide } from "@/lib/guides";

export const dynamicParams = false;

export function generateStaticParams() {
  return GUIDES.map((g) => ({ slug: g.slug }));
}

export function generateMetadata({ params }: { params: { slug: string } }): Metadata {
  const g = getGuide(params.slug);
  if (!g) return {};
  const url = `https://riseply.com/guides/${g.slug}`;
  return {
    title: `${g.title} | Riseply`,
    description: g.description,
    alternates: { canonical: url },
    openGraph: {
      title: g.title, description: g.description, url, siteName: "Riseply", type: "article",
      images: [{ url: "/brand/og.png", width: 1200, height: 630 }],
    },
    twitter: { card: "summary_large_image", images: ["/brand/og.png"] },
  };
}

export default function GuidePage({ params }: { params: { slug: string } }) {
  const g = getGuide(params.slug);
  if (!g) notFound();
  const url = `https://riseply.com/guides/${g.slug}`;
  const related = g.related.map((s) => getGuide(s)).filter((x): x is NonNullable<typeof x> => !!x);
  const jsonLd = [
    {
      "@context": "https://schema.org",
      "@type": "Article",
      headline: g.title,
      description: g.description,
      url,
      mainEntityOfPage: url,
      datePublished: GUIDES_PUBLISHED,
      dateModified: GUIDES_PUBLISHED,
      image: "https://riseply.com/brand/og.png",
      author: { "@type": "Organization", name: "Riseply", url: "https://riseply.com" },
      publisher: { "@type": "Organization", name: "Riseply", url: "https://riseply.com", logo: { "@type": "ImageObject", url: "https://riseply.com/brand/icon.svg" } },
    },
    {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "Riseply", item: "https://riseply.com/" },
        { "@type": "ListItem", position: 2, name: "Guides", item: "https://riseply.com/guides" },
        { "@type": "ListItem", position: 3, name: g.title, item: url },
      ],
    },
  ];
  return (
    <div className="auth-shell" style={{ alignItems: "flex-start", paddingTop: 60 }}>
      {jsonLd.map((d, i) => (
        <script key={i} type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(d) }} />
      ))}
      <main style={{ maxWidth: 680, margin: "0 auto" }}>
        <p className="hint"><Link href="/guides">All guides</Link></p>
        <h1>{g.title}</h1>
        <p style={{ fontSize: "1.05rem" }}><strong>{g.answer}</strong></p>
        <p className="hint">Published October 2026</p>

        {g.sections.map((s) => (
          <section key={s.h}>
            <h2 style={{ fontSize: "1.15rem" }}>{s.h}</h2>
            {s.p?.map((t) => <p key={t}>{t}</p>)}
            {s.ul && <ul>{s.ul.map((t) => <li key={t}>{t}</li>)}</ul>}
          </section>
        ))}

        <h2 style={{ fontSize: "1.15rem" }}>How Riseply helps</h2>
        <p>{g.riseply}</p>
        <div style={{ display: "flex", gap: 10, margin: "20px 0" }}>
          <Link href="/signup" className="btn btn-primary">Try Riseply free</Link>
          <Link href="/how-it-works" className="btn btn-ghost">How it works</Link>
        </div>

        {related.length > 0 && (
          <>
            <h2 style={{ fontSize: "1.15rem" }}>Related guides</h2>
            <ul>{related.map((r) => <li key={r.slug}><Link href={`/guides/${r.slug}`}>{r.title}</Link></li>)}</ul>
          </>
        )}
        <PublicFooter />
      </main>
    </div>
  );
}
