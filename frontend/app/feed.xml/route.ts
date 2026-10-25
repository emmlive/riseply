import { GUIDES, GUIDES_PUBLISHED } from "@/lib/guides";

export const dynamic = "force-static";

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function GET() {
  const pub = new Date(`${GUIDES_PUBLISHED}T12:00:00Z`).toUTCString();
  const items = GUIDES.map((g) => `    <item>
      <title>${esc(g.title)}</title>
      <link>https://riseply.com/guides/${g.slug}</link>
      <guid>https://riseply.com/guides/${g.slug}</guid>
      <pubDate>${pub}</pubDate>
      <description>${esc(g.answer)}</description>
    </item>`).join("\n");
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Riseply job search guides</title>
    <link>https://riseply.com/guides</link>
    <description>Plain answers to the questions job seekers ask most.</description>
    <language>en-us</language>
${items}
  </channel>
</rss>
`;
  return new Response(xml, { headers: { "Content-Type": "application/rss+xml; charset=utf-8" } });
}
