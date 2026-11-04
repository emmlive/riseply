"use client";

import { useState } from "react";
import { downloadPost } from "@/lib/api";

// Download the resume text exactly as it is on screen, edits included, as a
// Word file (to keep editing) or an ATS-friendly PDF (to upload). Nothing is
// saved by downloading.
export default function ResumeDownload({ text, name }: { text: string; name: string }) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function get(format: "docx" | "pdf") {
    if (busy || !text.trim()) return;
    setBusy(format); setError("");
    try {
      await downloadPost("/resumes/download", { text, format, name }, `resume.${format}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't make that file. Try again.");
    } finally {
      setBusy("");
    }
  }

  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
      <button className="btn btn-ghost btn-sm" onClick={() => get("docx")} disabled={!!busy || !text.trim()}>
        {busy === "docx" ? "Making Word file…" : "Download Word"}
      </button>
      <button className="btn btn-ghost btn-sm" onClick={() => get("pdf")} disabled={!!busy || !text.trim()}>
        {busy === "pdf" ? "Making PDF…" : "Download PDF"}
      </button>
      {error && <span role="alert" style={{ color: "#B23B3B", fontSize: 13 }}>{error}</span>}
    </div>
  );
}
