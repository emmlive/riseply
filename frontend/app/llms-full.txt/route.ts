import { FAQS, STAGES, UPDATED_LABEL } from "@/lib/publicContent";
import { GUIDES } from "@/lib/guides";

export const dynamic = "force-static";

// One plain-text file with the substance of the public site, for AI crawlers
// and assistants that prefer a single document. Built from the same data as
// the pages, so it cannot drift from them.
export function GET() {
  const out: string[] = [];
  out.push("# Riseply: full text", "");
  out.push(`Source: https://riseply.com. Last updated ${UPDATED_LABEL}.`, "");
  out.push("Riseply is an AI job-search platform. It matches new jobs to your resume every day, tailors an ATS-friendly resume for each job using only what is already in your resume, helps fill in application forms, prepares you for interviews, and coaches you into your next role. You approve every step; Riseply never applies or sends anything on its own.", "");
  out.push("## How it works (https://riseply.com/how-it-works)", "");
  for (const s of STAGES) {
    out.push(`### ${s.name}: ${s.summary}`);
    for (const w of s.what) out.push(`- ${w}`);
    out.push("");
  }
  out.push("## Frequently asked questions (https://riseply.com/faq)", "");
  for (const f of FAQS) out.push(`Q: ${f.q}`, `A: ${f.a}`, "");
  out.push("## Guides (https://riseply.com/guides)", "");
  for (const g of GUIDES) {
    out.push(`### ${g.title} (https://riseply.com/guides/${g.slug})`, g.answer, "");
    for (const s of g.sections) {
      out.push(`${s.h}`);
      for (const p of s.p ?? []) out.push(p);
      for (const u of s.ul ?? []) out.push(`- ${u}`);
      out.push("");
    }
    out.push(`How Riseply helps: ${g.riseply}`, "");
  }
  return new Response(out.join("\n"), { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
