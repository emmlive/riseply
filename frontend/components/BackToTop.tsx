"use client";

import { useEffect, useState } from "react";

// A round arrow in the corner that appears once the page has been scrolled
// a fair way, and takes the person back to the top in one click.
export default function BackToTop({ after = 500 }: { after?: number }) {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const onScroll = () => setShow(window.scrollY > after);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [after]);

  if (!show) return null;

  function goUp() {
    let smooth = true;
    try { smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch { /* keep default */ }
    window.scrollTo({ top: 0, behavior: smooth ? "smooth" : "auto" });
  }

  return (
    <button type="button" className="back-to-top" onClick={goUp} aria-label="Back to top" title="Back to top">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
           strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 19V5" /><path d="M5 12l7-7 7 7" />
      </svg>
    </button>
  );
}
