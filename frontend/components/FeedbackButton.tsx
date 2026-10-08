"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { api, FeedbackCategory } from "@/lib/api";

// "Give feedback" in the sidebar, on every dashboard page. A rating, a type
// and a few words; the page it was sent from is attached automatically.

const TYPES: { value: FeedbackCategory; label: string }[] = [
  { value: "idea", label: "An idea" },
  { value: "problem", label: "Something's broken" },
  { value: "praise", label: "Something I like" },
];
const RATING_WORDS = ["", "Poor", "Not great", "Okay", "Good", "Great"];

export default function FeedbackButton() {
  const [open, setOpen] = useState(false);
  const [rating, setRating] = useState(0);
  const [category, setCategory] = useState<FeedbackCategory | "">("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const pathname = usePathname();
  const firstRef = useRef<HTMLButtonElement>(null);

  const dirty = !sent && (rating > 0 || message.trim().length > 0);

  function reset() { setRating(0); setCategory(""); setMessage(""); setSent(false); setError(""); }
  function close() {
    if (dirty && !window.confirm("Close without sending your feedback?")) return;
    setOpen(false);
    reset();
  }

  useEffect(() => {
    if (!open) return;
    firstRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, dirty]);

  async function send() {
    if (sending || (rating === 0 && !message.trim())) return;
    setSending(true);
    setError("");
    try {
      await api("/feedback", {
        method: "POST",
        body: JSON.stringify({ rating: rating || null, category, message: message.trim(), page: pathname || "" }),
      });
      setSent(true);
    } catch (e: any) {
      setError(e?.message || "We couldn't send that. Please try again.");
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <button type="button" className="btn btn-ghost btn-sm fb-open" onClick={() => setOpen(true)}>
        Give feedback
      </button>
      {open && (
        <div className="fb-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) close(); }}>
          <div className="fb-dialog" role="dialog" aria-modal="true" aria-labelledby="fb-title">
            {sent ? (
              <div className="fb-done">
                <h2 id="fb-title">Thank you</h2>
                <p>We read every note, and it shapes what we build next.</p>
                <button className="btn btn-primary" onClick={() => { setOpen(false); reset(); }}>Close</button>
              </div>
            ) : (
              <>
                <h2 id="fb-title">Share your feedback</h2>
                <p className="hint" style={{ margin: "2px 0 14px" }}>Tell us what works and what doesn&apos;t. A rating alone is fine.</p>

                <div className="fb-label" id="fb-rating-label">How is Riseply working for you?</div>
                <div className="fb-stars" role="radiogroup" aria-labelledby="fb-rating-label">
                  {[1, 2, 3, 4, 5].map((n, i) => (
                    <button
                      key={n} type="button" role="radio" aria-checked={rating === n}
                      aria-label={`${n} star${n === 1 ? "" : "s"}, ${RATING_WORDS[n]}`}
                      className={`fb-star ${n <= rating ? "on" : ""}`}
                      ref={i === 0 ? firstRef : undefined}
                      onClick={() => setRating(rating === n ? 0 : n)}
                    >★</button>
                  ))}
                  <span className="fb-rating-word" aria-live="polite">{RATING_WORDS[rating]}</span>
                </div>

                <div className="fb-label">What kind of feedback is it?</div>
                <div className="cc-seg" role="radiogroup" aria-label="Type of feedback">
                  {TYPES.map((t) => (
                    <label key={t.value} className="cc-pill">
                      <input type="radio" name="fb-type" checked={category === t.value}
                             onChange={() => setCategory(t.value)} onClick={() => category === t.value && setCategory("")} />
                      <span>{t.label}</span>
                    </label>
                  ))}
                </div>

                <label className="fb-label" htmlFor="fb-message">Anything you&apos;d like to add?</label>
                <textarea id="fb-message" className="cc-input" rows={4} maxLength={2000} value={message}
                          onChange={(e) => setMessage(e.target.value)}
                          placeholder="What were you trying to do? What would make it better?" />
                <div className="hint fb-foot-hint">Sent from {pathname || "this page"}. We don&apos;t read your coaching conversations from this.</div>

                {error && <p className="cc-error" role="alert">{error}</p>}
                <div className="fb-actions">
                  <button className="btn btn-ghost" onClick={close}>Cancel</button>
                  <button className="btn btn-primary" onClick={send} disabled={sending || (rating === 0 && !message.trim())}>
                    {sending ? "Sending…" : "Send feedback"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
