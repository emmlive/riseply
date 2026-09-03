"use client";

import { useEffect, useState } from "react";
import { api, Organization, Application } from "@/lib/api";

const INDIVIDUAL_FAQ = [
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

// Distinct from INDIVIDUAL_FAQ above rather than a filtered subset --
// the two audiences' actual questions barely overlap (an org-affiliated
// person has never seen "search profiles" or "Rise Index" in their own
// nav, so an FAQ entry explaining those would be explaining something
// they can't access in the first place). Kept as a single combined list
// covering both admin setup questions and employee privacy questions,
// rather than splitting further by admin/employee -- both audiences
// plausibly wonder about either topic (an admin cares about privacy
// too; an employee might wonder how matching/setup works), and a
// three-way FAQ split for this small a list isn't worth the added
// complexity yet.
const ORG_FAQ = [
  {
    q: "How does mentor matching work?",
    a: "When an admin clicks \"Suggest mentors (AI),\" Claude scores each eligible mentor against the employee's resume and stated career goal and explains its reasoning in plain language. It's advisory only — an admin always makes the final assignment.",
  },
  {
    q: "Can admins see what employees discuss with their mentor or in Job Buddy chat?",
    a: "No. Conversation content and meeting notes stay private to the employee. Admins only ever see aggregate program-health numbers — pairing counts, meeting frequency, average feedback rating — never the actual words exchanged.",
  },
  {
    q: "How do internal job postings work?",
    a: "An admin posts an opening (title, department, description) from Internal Jobs. It shows up on employees' Job Buddy page, and they apply using the resume already on file — no fresh upload, no external tailoring.",
  },
  {
    q: "Can employees search for jobs outside the company through this?",
    a: "No — external job search is intentionally not part of the organization experience. Internal Jobs covers finding a next role within your own company instead.",
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
  // Same org-affiliation check as dashboard/page.tsx and layout.tsx --
  // null while unresolved so the individual FAQ doesn't flash briefly
  // for an org-affiliated person before swapping to the org one.
  const [isOrgAffiliated, setIsOrgAffiliated] = useState<boolean | null>(null);

  useEffect(() => {
    Promise.all([
      api<Organization[]>("/orgs/mine").catch(() => []),
      api<Application[]>("/applications").catch(() => []),
    ]).then(([orgs, apps]) => {
      setIsOrgAffiliated(orgs.length > 0 || apps.some((a) => a.organization_id !== null));
    });
  }, []);

  const FAQ = isOrgAffiliated ? ORG_FAQ : INDIVIDUAL_FAQ;

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
      {isOrgAffiliated !== null && FAQ.map((item) => (
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
