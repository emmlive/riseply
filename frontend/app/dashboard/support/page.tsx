"use client";

import { useState } from "react";
import { api } from "@/lib/api";

const FAQ = [
  {
    q: "How does matching work?",
    a: "Every job posting is scored against your resume and each of your active search profiles using Claude. It only gets queued for your review if it clears that profile's minimum match score.",
  },
  {
    q: "Will Riseply submit applications for me automatically?",
    a: "No. You review and approve every match, and you mark it \"applied\" yourself once you've actually submitted it on the company's site. Nothing goes out without you.",
  },
  {
    q: "What's the difference between Free and Pro?",
    a: "Pro gives you roughly 5x higher monthly limits on matching, resume tailoring, interview prep, and Job Buddy, plus up to 10 simultaneous search profiles instead of 1. See the Billing tab for exact numbers.",
  },
  {
    q: "What is the Rise Index?",
    a: "Live, anonymized response-rate stats pulled from everyone using Riseply — e.g. \"68% of applicants heard back from Acme Corp within 9 days.\" A company only shows up once enough people have applied to keep individuals unidentifiable.",
  },
  {
    q: "Can I delete my account?",
    a: "Reach out below and we'll take care of it.",
  },
];

export default function SupportPage() {
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  async function send() {
    setSending(true);
    setError("");
    try {
      await api("/support/contact", { method: "POST", body: JSON.stringify({ subject, message }) });
      setSent(true);
      setSubject("");
      setMessage("");
    } catch (err: any) {
      setError(err.message || "Couldn't send your message — try again in a moment.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div>
      <h1>Support</h1>

      <h2 style={{ marginTop: 8 }}>Common questions</h2>
      {FAQ.map((item) => (
        <div key={item.q} className="card">
          <h3 style={{ fontSize: "0.95rem" }}>{item.q}</h3>
          <p style={{ margin: 0 }}>{item.a}</p>
        </div>
      ))}

      <h2 style={{ marginTop: 28 }}>Still need help?</h2>

      {sent ? (
        <div className="card" style={{ borderColor: "var(--accent)" }}>
          Sent — we'll get back to you at your account email.
          <div style={{ marginTop: 10 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setSent(false)}>Send another message</button>
          </div>
        </div>
      ) : (
        <div className="card">
          <div className="field">
            <label>Subject</label>
            <input value={subject} onChange={(e) => setSubject(e.target.value)}
                   placeholder="What's this about?" />
          </div>
          <div className="field">
            <label>Message</label>
            <textarea rows={6} value={message} onChange={(e) => setMessage(e.target.value)}
                      placeholder="Tell us what's going on…" />
          </div>
          {error && <p className="error-text">{error}</p>}
          <button className="btn btn-primary" onClick={send} disabled={sending || !subject.trim() || !message.trim()}>
            {sending ? "Sending…" : "Send message"}
          </button>
        </div>
      )}
    </div>
  );
}
