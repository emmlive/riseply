import { Fragment, ReactNode } from "react";

// Shows the simple markdown the Task guide writes (headings, tables, lists,
// checkboxes, bold, rules) as a formatted document. Built from React
// elements, never raw HTML, so nothing the model writes can run as code.

function inline(text: string): ReactNode[] {
  return text.replace(/`/g, "").split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((p, i) =>
    p.startsWith("**") && p.endsWith("**") && p.length > 4 ? <strong key={i}>{p.slice(2, -2)}</strong> : <Fragment key={i}>{p}</Fragment>
  );
}

function cells(line: string): string[] {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((c) => c.trim());
}

const ROW = /^\s*\|.*\|\s*$/;
const SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

export default function MiniMarkdown({ text }: { text: string }) {
  const lines = (text || "").replace(/\r\n/g, "\n").split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  let k = 0;
  while (i < lines.length) {
    const s = lines[i].trim();
    if (!s) { i++; continue; }
    const h = s.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      const level = Math.min(h[1].length, 4);
      out.push(<div key={k++} className={`md-h md-h${level}`} role="heading" aria-level={level + 1}>{inline(h[2])}</div>);
      i++; continue;
    }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(s)) { out.push(<hr key={k++} className="md-rule" />); i++; continue; }
    if (ROW.test(s) && i + 1 < lines.length && SEP.test(lines[i + 1].trim()) && lines[i + 1].includes("|")) {
      const head = cells(s);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && ROW.test(lines[i].trim())) { rows.push(cells(lines[i])); i++; }
      out.push(
        <div key={k++} className="md-table-wrap">
          <table className="md-table">
            <thead><tr>{head.map((c, j) => <th key={j}>{inline(c)}</th>)}</tr></thead>
            <tbody>{rows.map((r, a) => <tr key={a}>{head.map((_, j) => <td key={j}>{inline(r[j] || "")}</td>)}</tr>)}</tbody>
          </table>
        </div>
      );
      continue;
    }
    const bullet = /^[-*•]\s+(.*)$/;
    const number = /^\d+[.)]\s+(.*)$/;
    if (bullet.test(s) || number.test(s)) {
      const ordered = number.test(s);
      const re = ordered ? number : bullet;
      const items: { text: string; check: boolean | null }[] = [];
      while (i < lines.length) {
        const m = lines[i].trim().match(re);
        if (!m) break;
        const c = m[1].match(/^\[( |x|X)\]\s+(.*)$/);
        items.push(c ? { text: c[2], check: c[1].toLowerCase() === "x" } : { text: m[1], check: null });
        i++;
      }
      const body = items.map((it, a) => (
        <li key={a} className={it.check !== null ? "md-check" : undefined}>
          {it.check !== null && <span aria-hidden="true">{it.check ? "☑ " : "☐ "}</span>}
          {inline(it.text)}
        </li>
      ));
      out.push(ordered ? <ol key={k++} className="md-list">{body}</ol> : <ul key={k++} className="md-list">{body}</ul>);
      continue;
    }
    out.push(<p key={k++} className="md-p">{inline(s)}</p>);
    i++;
  }
  return <div className="md">{out}</div>;
}

export function hasTable(text: string): boolean {
  const lines = (text || "").split("\n");
  return lines.some((l, i) => ROW.test(l.trim()) && i + 1 < lines.length && SEP.test(lines[i + 1].trim()) && lines[i + 1].includes("|"));
}
