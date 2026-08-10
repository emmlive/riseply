"use client";

import { useEffect, useRef, useState } from "react";
import { api, SavedResume } from "@/lib/api";

export default function ResumePage() {
  const [resumes, setResumes] = useState<SavedResume[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [label, setLabel] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<SavedResume[]>("/resumes").then((list) => {
      setResumes(list);
      const active = list.find((r) => r.is_default) || list[0];
      if (active) {
        setActiveId(active.id);
        setLabel(active.label);
        setResumeText(active.resume_text);
      }
      setLoaded(true);
    });
  }, []);

  function selectResume(r: SavedResume) {
    setActiveId(r.id);
    setLabel(r.label);
    setResumeText(r.resume_text);
    setSaved(false);
    setError("");
  }

  function startNewResume() {
    setActiveId(null);
    setLabel(`Resume ${resumes.length + 1}`);
    setResumeText("");
    setSaved(false);
    setError("");
  }

  async function save() {
    if (!resumeText.trim()) {
      setError("Add some resume text before saving.");
      return;
    }
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      if (activeId === null) {
        const created = await api<SavedResume>("/resumes", {
          method: "POST",
          body: JSON.stringify({ label: label.trim(), resume_text: resumeText }),
        });
        setResumes((prev) => [created, ...prev.map((r) => ({ ...r, is_default: created.is_default ? false : r.is_default }))]);
        setActiveId(created.id);
      } else {
        const updated = await api<SavedResume>(`/resumes/${activeId}`, {
          method: "PATCH",
          body: JSON.stringify({ label: label.trim(), resume_text: resumeText }),
        });
        setResumes((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err: any) {
      setError(err.message || "Couldn't save your resume.");
    } finally {
      setSaving(false);
    }
  }

  async function setDefault(id: number) {
    try {
      await api(`/resumes/${id}/set-default`, { method: "POST" });
      setResumes((prev) => prev.map((r) => ({ ...r, is_default: r.id === id })));
    } catch (err: any) {
      setError(err.message || "Couldn't set that as default.");
    }
  }

  async function deleteResume(id: number) {
    if (!confirm("Delete this resume? This can't be undone.")) return;
    try {
      await api(`/resumes/${id}`, { method: "DELETE" });
      const remaining = resumes.filter((r) => r.id !== id);
      setResumes(remaining);
      if (activeId === id) {
        const nextActive = remaining.find((r) => r.is_default) || remaining[0];
        if (nextActive) selectResume(nextActive);
        else startNewResume();
      }
    } catch (err: any) {
      setError(err.message || "Couldn't delete that resume.");
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

  if (!loaded) return <div><h1>Resume</h1></div>;

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
        Your <strong>default</strong> resume is what gets matched against job postings and
        rewritten per job — nothing here is invented, only reordered and re-emphasized for each
        application.
      </p>

      {resumes.length > 0 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          {resumes.map((r) => (
            <button
              key={r.id}
              className="btn btn-ghost btn-sm"
              onClick={() => selectResume(r)}
              style={r.id === activeId ? { background: "var(--accent-soft)", color: "var(--accent-hover)", borderColor: "var(--accent)" } : {}}
            >
              {r.is_default && "★ "}{r.label}
            </button>
          ))}
          <button className="btn btn-ghost btn-sm" onClick={startNewResume}>+ Add another resume</button>
        </div>
      )}

      {activeId !== null && (
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 12 }}>
          {!resumes.find((r) => r.id === activeId)?.is_default && (
            <button className="btn btn-ghost btn-sm" onClick={() => setDefault(activeId)}>Set as default</button>
          )}
          <button className="btn btn-ghost btn-sm" onClick={() => deleteResume(activeId)}>Delete this resume</button>
        </div>
      )}

      <div className="field" style={{ marginBottom: 12 }}>
        <label>Resume name</label>
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Security Engineer resume" />
      </div>

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
