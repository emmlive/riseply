import Link from "next/link";

// Links every public page to the others, so a reader (or a crawler) can reach
// the whole site from any page.
export default function PublicFooter() {
  return (
    <nav aria-label="Riseply" className="muted" style={{ marginTop: 40, paddingTop: 16, borderTop: "1px solid var(--border)", fontSize: "0.85rem", lineHeight: 1.9 }}>
      <Link href="/">Home</Link> · <Link href="/how-it-works">How it works</Link> · <Link href="/faq">FAQ</Link> ·{" "}
      <Link href="/riseply-vs-alternatives">Riseply vs. alternatives</Link> · <Link href="/riseply-enterprise">Riseply Enterprise</Link> ·{" "}
      <Link href="/security">Security &amp; Trust</Link> · <Link href="/privacy">Privacy</Link> · <Link href="/terms">Terms</Link>
    </nav>
  );
}
