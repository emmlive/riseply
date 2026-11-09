// Study notes are stored as plain text with a few light marks that still read
// fine as plain text: "# " title, "## " section, "### " sub-heading, "- " bullets,
// "1. " numbered steps, "Answer: " under a numbered question, **bold**.
// This turns that text into blocks the page lays out neatly (and the print view
// uses). A note with no marks at all is just paragraphs, so everything saved
// before this existed still displays.

export type Inline = { b: boolean; v: string };
export type Block =
  | { t: "h1" | "h2" | "h3"; text: string }
  | { t: "meta"; text: string }
  | { t: "p"; text: string }
  | { t: "ul"; items: string[] }
  | { t: "ol"; items: { text: string; answer?: string }[] };

export function inline(text: string): Inline[] {
  const out: Inline[] = [];
  const re = /\*\*([^*]+)\*\*/g;
  let last = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m.index > last) out.push({ b: false, v: text.slice(last, m.index) });
    out.push({ b: true, v: m[1] });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ b: false, v: text.slice(last) });
  return out;
}

const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBER = /^\s*\d{1,2}[.)]\s+(.*)$/;
const HEAD = /^(#{1,3})\s+(.*)$/;
const ANSWER = /^\s*Answer:\s*(.*)$/i;

export function parseNote(content: string): Block[] {
  const blocks: Block[] = [];
  let para: string[] = [];
  const flush = () => { if (para.length) { blocks.push({ t: "p", text: para.join("\n") }); para = []; } };
  for (const raw of (content || "").replace(/\r\n?/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    const head = line.match(HEAD);
    const bullet = line.match(BULLET);
    const num = line.match(NUMBER);
    const ans = line.match(ANSWER);
    const last = blocks[blocks.length - 1];
    if (!line.trim()) { flush(); continue; }
    if (head) {
      flush();
      blocks.push({ t: (["h1", "h2", "h3"] as const)[head[1].length - 1], text: head[2].trim() });
    } else if (bullet) {
      flush();
      if (last && last.t === "ul") last.items.push(bullet[1]);
      else blocks.push({ t: "ul", items: [bullet[1]] });
    } else if (num) {
      flush();
      if (last && last.t === "ol") last.items.push({ text: num[1] });
      else blocks.push({ t: "ol", items: [{ text: num[1] }] });
    } else if (ans && last && last.t === "ol" && para.length === 0) {
      last.items[last.items.length - 1].answer = ans[1];
    } else {
      // The line right under the title ("Course · Studied Nov 8, 2026") is a subtitle.
      if (last && last.t === "h1" && para.length === 0 && blocks.filter((b) => b.t === "meta").length === 0) {
        blocks.push({ t: "meta", text: line.trim() });
      } else {
        para.push(line);
      }
    }
  }
  flush();
  return blocks;
}

// The recap shown at the end of a module, in the same note form.
export function recapToMarkdown(r: {
  summary: string; key_points: string[]; terms: { term: string; meaning: string }[]; walkthrough?: string[];
  example?: string; story?: string; watch_out?: string[]; check_yourself?: { q: string; a: string }[];
  practice?: string; shaky?: string[]; next_up?: string;
}): string {
  const L: string[] = ["## Summary", r.summary, "", "## Key points", ...r.key_points.map((p) => `- ${p}`)];
  const section = (head: string, lines: string[]) => { if (lines.length) L.push("", `## ${head}`, ...lines); };
  section("Terms to know", (r.terms || []).map((t) => `- **${t.term}**: ${t.meaning}`));
  section("How to think about it", (r.walkthrough || []).map((x, i) => `${i + 1}. ${x}`));
  section("Example", r.example ? [r.example] : []);
  section("Story to remember", r.story ? [r.story] : []);
  section("Watch out for", (r.watch_out || []).map((x) => `- ${x}`));
  section("Check yourself", (r.check_yourself || []).flatMap((c, i) => [`${i + 1}. ${c.q}`, ...(c.a ? [`Answer: ${c.a}`] : [])]));
  section("Look at again", (r.shaky || []).map((x) => `- ${x}`));
  section("Before the next module", r.practice ? [r.practice] : []);
  section("Next", r.next_up ? [r.next_up] : []);
  return L.join("\n");
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const inl = (s: string) => inline(s).map((x) => (x.b ? `<strong>${esc(x.v)}</strong>` : esc(x.v))).join("");

// A printable page for one note (the browser's print dialog can save it as a PDF).
export function noteToPrintHtml(title: string, content: string): string {
  const body = parseNote(content).map((b) => {
    switch (b.t) {
      case "h1": return `<h1>${esc(b.text)}</h1>`;
      case "meta": return `<p class="meta">${esc(b.text)}</p>`;
      case "h2": return `<h2>${esc(b.text)}</h2>`;
      case "h3": return `<h3>${esc(b.text)}</h3>`;
      case "p": return `<p>${inl(b.text).replace(/\n/g, "<br>")}</p>`;
      case "ul": return `<ul>${b.items.map((i) => `<li>${inl(i)}</li>`).join("")}</ul>`;
      case "ol": return `<ol>${b.items.map((i) => `<li>${inl(i.text)}${i.answer ? `<div class="ans">Answer: ${inl(i.answer)}</div>` : ""}</li>`).join("")}</ol>`;
    }
  }).join("\n");
  const hasTitle = parseNote(content).some((b) => b.t === "h1");
  return `<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title><style>
  @page { margin: 18mm; }
  body { font: 11.5pt/1.55 Georgia, "Times New Roman", serif; color: #1b2433; max-width: 680px; margin: 0 auto; }
  h1 { font-size: 21pt; margin: 0 0 4px; line-height: 1.2; }
  .meta { color: #5b6478; font: 10pt system-ui, sans-serif; margin: 0 0 18px; }
  h2 { font: 700 10.5pt system-ui, sans-serif; letter-spacing: .02em; color: #1f7a6c; margin: 20px 0 6px; padding-bottom: 3px; border-bottom: 1.5px solid #cfe3de; break-after: avoid; }
  h3 { font: 600 10.5pt system-ui, sans-serif; margin: 12px 0 2px; }
  p { margin: 6px 0; } ul, ol { margin: 6px 0; padding-left: 22px; } li { margin: 3px 0; break-inside: avoid; }
  .ans { color: #4a5568; font-style: italic; font-size: 10.5pt; margin-top: 1px; }
  </style></head><body>${hasTitle ? "" : `<h1>${esc(title)}</h1>`}${body}</body></html>`;
}

// Opens the print dialog for a note without a pop-up window.
export function printNote(title: string, content: string): void {
  const frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
  document.body.appendChild(frame);
  const doc = frame.contentDocument;
  if (!doc || !frame.contentWindow) { frame.remove(); return; }
  doc.open(); doc.write(noteToPrintHtml(title, content)); doc.close();
  const win = frame.contentWindow;
  setTimeout(() => {
    try { win.focus(); win.print(); } finally { setTimeout(() => frame.remove(), 1500); }
  }, 150);
}
