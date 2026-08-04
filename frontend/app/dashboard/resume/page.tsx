"use client";

import { useEffect, useState } from "react";
import { api, User } from "@/lib/api";

export default function ResumePage() {
  const [resumeText, setResumeText] = useState("");
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api<User>("/me").then((u) => setResumeText(u.resume_text));
  }, []);

  async function save() {
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      await api("/me/resume", { method: "PUT", body: JSON.stringify({ resume_text: resumeText }) });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err: any) {
      setError(err.message || "Couldn't save your resume.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="topbar">
        <h1>Resume</h1>
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save resume"}
        </button>
      </div>
      <p className="muted">
        Paste your resume as plain text. This is what gets matched against
        job postings and rewritten per job — nothing here is invented,
        only reordered and re-emphasized for each application.
      </p>

      <div className="field">
        <textarea
          rows={24}
          value={resumeText}
          onChange={(e) => setResumeText(e.target.value)}
          placeholder="Paste your resume text here…"
        />
      </div>

      {saved && <p style={{ color: "var(--accent)" }}>Saved.</p>}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}
