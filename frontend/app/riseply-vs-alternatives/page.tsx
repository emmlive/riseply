import Link from "next/link";
import type { Metadata } from "next";
import PublicFooter from "@/components/PublicFooter";
import { UPDATED, UPDATED_LABEL } from "@/lib/publicContent";

const URL = "https://riseply.com/riseply-vs-alternatives";

export const metadata: Metadata = {
  title: "Riseply vs. alternatives: spreadsheets, chatbots, auto-apply bots and coaches",
  description:
    "An honest comparison of Riseply with the other ways to run a job search: a spreadsheet, a general AI chatbot, auto-apply bots, resume builders and human career coaches. Where each one is the better choice.",
  alternates: { canonical: URL },
  openGraph: {
    title: "Riseply vs. alternatives", description: "Where Riseply fits, and where something else is the better choice.",
    url: URL, siteName: "Riseply", type: "article",
    images: [{ url: "/brand/og.png", width: 1200, height: 630 }],
  },
  twitter: { card: "summary_large_image", images: ["/brand/og.png"] },
};

const ROWS: { option: string; good: string; gap: string; pick: string }[] = [
  {
    option: "A spreadsheet and your own writing",
    good: "Free, fully under your control, no learning curve.",
    gap: "You find every job, rewrite every resume and track every follow-up by hand, which is slow and easy to let slip.",
    pick: "You are applying to a handful of roles and enjoy doing it yourself.",
  },
  {
    option: "A general AI chatbot (ChatGPT, Claude and similar)",
    good: "Flexible. Good for rewording a paragraph or brainstorming answers, with no setup.",
    gap: "It does not find jobs, remember what you applied to, or connect your resume to each posting. You paste everything in each time, and it will happily write experience you do not have if you let it.",
    pick: "You need one-off writing help.",
  },
  {
    option: "Auto-apply bots",
    good: "Very high volume with almost no effort.",
    gap: "Bulk applications often carry generic or wrong answers and tend to get fewer replies, and some employers filter them out. You can also lose track of what was sent in your name.",
    pick: "You want sheer volume more than fit and are comfortable with the risk.",
  },
  {
    option: "Resume builders and ATS checkers",
    good: "Clean templates and a keyword score for one resume against one job description.",
    gap: "They stop at the document. They do not find roles, fill in the application, or prepare you for the interview.",
    pick: "Your main problem is the format of your resume.",
  },
  {
    option: "A human career coach",
    good: "Real judgment, industry contacts, and accountability from a person.",
    gap: "Costly, limited hours, and no help with the daily mechanics of searching and applying.",
    pick: "You want personal strategy, introductions or support through a hard transition. Many people use a coach and Riseply together.",
  },
  {
    option: "Riseply",
    good: "Connects the whole loop in one place: daily job matching, a tailored ATS resume per job, form filling in Chrome, tracking and follow-ups, interview prep, a Career Coach, skill-gap and career-path plans. Built on a no-invention rule, and you approve every step.",
    gap: "It does not mass-apply for you, it cannot make introductions, and form filling still leaves some questions for you on complicated application sites. The Chrome extension is not in the Chrome Web Store yet.",
    pick: "You want a steady, honest search with less busywork, and help growing into the next role.",
  },
];

const JSON_LD = [
  {
    "@context": "https://schema.org",
    "@type": "WebPage",
    name: "Riseply vs. alternatives",
    url: URL,
    dateModified: UPDATED,
    isPartOf: { "@type": "WebSite", name: "Riseply", url: "https://riseply.com" },
  },
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Riseply", item: "https://riseply.com/" },
      { "@type": "ListItem", position: 2, name: "Riseply vs. alternatives", item: URL },
    ],
  },
];

export default function VsPage() {
  return (
    <div className="auth-shell" style={{ alignItems: "flex-start", paddingTop: 60 }}>
      {JSON_LD.map((d, i) => (
        <script key={i} type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(d) }} />
      ))}
      <main style={{ maxWidth: 680, margin: "0 auto" }}>
        <h1>Riseply vs. the alternatives</h1>
        <p style={{ fontSize: "1.05rem" }}>
          Riseply is best for people who want a steady, honest job search with less busywork: it finds and scores
          jobs, tailors a resume for each, helps with applications and interviews, and never applies without your
          approval. Other approaches are better in some situations, and this page says which.
        </p>
        <p className="hint">Last updated {UPDATED_LABEL}. Descriptions are of each approach in general, not of any one product.</p>

        {ROWS.map((r) => (
          <section key={r.option}>
            <h2 style={{ fontSize: "1.15rem" }}>{r.option}</h2>
            <ul>
              <li><strong>Good at:</strong> {r.good}</li>
              <li><strong>Falls short:</strong> {r.gap}</li>
              <li><strong>Pick it when:</strong> {r.pick}</li>
            </ul>
          </section>
        ))}

        <h2>The short version</h2>
        <p>
          If you only need a sentence reworded, use a chatbot. If you need a person to open doors, hire a coach. If
          you are running a real search over weeks and want one place that finds the jobs, prepares each
          application honestly and keeps you moving, that is what Riseply is for.
        </p>
        <div style={{ display: "flex", gap: 10, margin: "24px 0" }}>
          <Link href="/signup" className="btn btn-primary">Get started free</Link>
          <Link href="/how-it-works" className="btn btn-ghost">How it works</Link>
        </div>
        <PublicFooter />
      </main>
    </div>
  );
}
