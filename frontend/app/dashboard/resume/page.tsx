"use client";

import { useEffect, useRef, useState } from "react";
import { api, User } from "@/lib/api";

export default function ResumePage() {
  const [resumeText, setResumeText] = useState("");
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  async function handleFile(file: File) {
    setParsing(true);
    setError("");
    setSaved(false);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const result = await api<{ resume_text: string }>("/me/resume/parse", {
        method: "POST",
        body: formData,
      });
      setResumeText(result.resume_text);
    } catch (err: any) {
      setError(err.message || "Couldn't read that file.");
    } finally {
      setParsing(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragActive(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  function onFileInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = ""; // allow re-selecting the same file later
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
        Upload a PDF or Word doc, or paste your resume as plain text below.
        This is what gets matched against job postings and rewritten per
        job — nothing here is invented, only reordered and re-emphasized
        for each application.
      </p>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={onDrop}
        onClick={() => fileInputRef.current?.click()}
        style={{
          border: `2px dashed ${dragActive ? "var(--accent)" : "var(--border-strong)"}`,
          borderRadius: 12,
          padding: "28px 20px",
          textAlign: "center",
          cursor: "pointer",
          background: dragActive ? "var(--accent-soft)" : "var(--surface)",
          marginBottom: 16,
          transition: "background 0.15s, border-color 0.15s",
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx"
          onChange={onFileInputChange}
          style={{ display: "none" }}
        />
        {parsing ? (
          <p style={{ margin: 0 }} className="muted">Reading your resume…</p>
        ) : (
          <>
            <p style={{ margin: 0, fontWeight: 600 }}>Drop a PDF or .docx here, or click to browse</p>
            <p className="hint" style={{ marginTop: 4 }}>We'll extract the text below for you to review before saving.</p>
          </>
        )}
      </div>

      <div className="field">
        <textarea
          rows={20}
          value={resumeText}
          onChange={(e) => setResumeText(e.target.value)}
          placeholder="Paste your resume text here, or upload a file above…"
        />
      </div>

      {saved && <p style={{ color: "var(--accent)" }}>Saved.</p>}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}
