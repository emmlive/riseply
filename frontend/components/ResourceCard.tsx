import { LibraryItem } from "@/lib/api";

// A single Library resource as a compact link card. Used in the coach's
// chat, the suggested-reading shelf, and the Library page. Links are
// only ever rendered for http(s) URLs (the backend enforces this too) and
// open in a new tab without leaking the opener.

export function isSafeUrl(url: string): boolean {
  return /^https?:\/\//i.test(url);
}

const TYPE_LABEL: Record<string, string> = {
  course: "Course", article: "Article", video: "Video", book: "Book",
  practice: "Practice", reference: "Reference", tool: "Tool",
};

export default function ResourceCard({ item, compact = false }: { item: LibraryItem; compact?: boolean }) {
  const meta = [TYPE_LABEL[item.resource_type] ?? item.resource_type, item.cost, item.level === "all" ? null : item.level]
    .filter(Boolean).join(" · ");
  const body = (
    <>
      <div style={{ fontWeight: 600 }}>{item.title} <span aria-hidden>↗</span></div>
      <div className="hint">{meta}</div>
      {!compact && item.description && <div style={{ marginTop: 4, fontSize: 14 }}>{item.description}</div>}
      {!compact && item.fields.length > 0 && (
        <div className="hint" style={{ marginTop: 4 }}>{item.fields.join(", ")}</div>
      )}
    </>
  );
  const style: React.CSSProperties = {
    display: "block", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 12px",
    marginTop: 8, textDecoration: "none", color: "inherit", background: "var(--paper)",
  };
  return isSafeUrl(item.url) ? (
    <a href={item.url} target="_blank" rel="noopener noreferrer" style={style}>{body}</a>
  ) : (
    <div style={style}>{body}</div>
  );
}
