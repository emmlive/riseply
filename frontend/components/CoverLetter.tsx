"use client";

import { useEffect, useRef, useState } from "react";
import { api, downloadFile } from "@/lib/api";

// A tailored cover letter for one application. It is written from the
// tailored resume and the posting, the person edits it freely, and
// Download builds the Word file from whatever is saved.

type Letter = { text: string; company: string; title: string };

export default function CoverLetter({
  applicationId,
  company,
  onClose,
  onChanged,
}: {
  applicationId: number;
  company: string;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const [saved, setSaved] = useState<string | null>(null);   // null while loading
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState<"" | "writing" | "saving" | "downloading" | "humanizing">("");
  const [before, setBefore] = useState<string | null>(null);   // draft before the last rewrite, for Undo
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const closeRef = useRef<HTMLButtonElement>(null);

  const dirty = saved !== null && draft !== saved;
  const words = draft.trim() ? draft.trim().split(/\s+/).length : 0;

  useEffect(() => {
    let cancelled = false;
    api<Letter>(`/applications/${applicationId}/cover-letter`)
      .then((d) => { if (!cancelled) { setSaved(d.text); setDraft(d.text); } })
      .catch((e) => { if (!cancelled) { setSaved(""); setError(e?.message || "We couldn't load this letter."); } });
    return () => { cancelled = true; };
  }, [applicationId]);

  function requestClose() {
    if (dirty && !window.confirm("Close without saving? Your edits will be lost.")) return;
    onClose();
  }

  useEffect(() => {
    closeRef.current?.focus();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, []);

  const closeRef2 = useRef(requestClose);
  closeRef2.current = requestClose;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") closeRef2.current(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  async function write() {
    if (saved && !window.confirm("Write a new letter? It replaces this one, including your edits.")) return;
    setBusy("writing");
    setError("");
    try {
      const d = await api<Letter>(`/applications/${applicationId}/cover-letter`, { method: "POST" });
      setSaved(d.text);
      setDraft(d.text);
      setBefore(null);
      setNote("");
      onChanged?.();
    } catch (e: any) {
      setError(e?.message || "Couldn't write the letter right now. Try again shortly.");
    } finally {
      setBusy("");
    }
  }

  async function humanize() {
    if (dirty && !(await save())) return;
    setBusy("humanizing");
    setError("");
    setNote("");
    try {
      const d = await api<{ text: string; note: string }>(`/applications/${applicationId}/cover-letter/humanize`, { method: "POST" });
      setBefore(draft);
      setDraft(d.text);
      setNote(`${d.note} This is a draft: read it, then press Save changes, or Undo to go back.`);
    } catch (e: any) {
      setError(e?.message || "Couldn't rewrite the letter right now. Try again shortly.");
    } finally {
      setBusy("");
    }
  }

  function undo() {
    if (before !== null) setDraft(before);
    setBefore(null);
    setNote("");
  }

  async function save(): Promise<boolean> {
    setBusy("saving");
    setError("");
    try {
      const d = await api<Letter>(`/applications/${applicationId}/cover-letter`, {
        method: "PUT",
        body: JSON.stringify({ text: draft }),
      });
      setSaved(d.text);
      setDraft(d.text);
      setBefore(null);
      setNote("");
      onChanged?.();
      return true;
    } catch (e: any) {
      setError(e?.message || "Couldn't save your changes.");
      return false;
    } finally {
      setBusy("");
    }
  }

  async function download() {
    if (dirty && !(await save())) return;
    setBusy("downloading");
    setError("");
    try {
      await downloadFile(`/applications/${applicationId}/cover-letter/download`, "Cover_Letter.docx");
    } catch (e: any) {
      setError(e?.message || "Couldn't download that file.");
    } finally {
      setBusy("");
    }
  }

  const hasLetter = !!saved;

  return (
    <div className="rp-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) requestClose(); }}>
      <div className="rp-dialog" role="dialog" aria-modal="true" aria-label={`Cover letter for ${company}`}>
        <header className="rp-head">
          <div>
            <h2 className="rp-title">Cover letter</h2>
            <p className="hint">For {company}. Written from your tailored resume and the posting.</p>
          </div>
          <div className="rp-actions">
            {hasLetter && dirty && (
              <button className="btn btn-primary btn-sm" onClick={save} disabled={busy !== ""}>
                {busy === "saving" ? "Saving…" : "Save changes"}
              </button>
            )}
            {hasLetter && (
              <button className={`btn btn-sm ${dirty ? "btn-ghost" : "btn-primary"}`} onClick={download} disabled={busy !== ""}>
                {busy === "downloading" ? "Downloading…" : "Download .docx"}
              </button>
            )}
            <button ref={closeRef} className="btn btn-ghost btn-sm" onClick={requestClose}>Close</button>
          </div>
        </header>

        <div className="rp-body">
          {error && <p className="cc-error" role="alert">{error}</p>}
          {saved === null && !error && <p className="hint">Loading…</p>}

          {saved !== null && !hasLetter && (
            <div className="brief rp-why">
              <p style={{ marginTop: 0 }}>
                Riseply writes a short letter for this job from the points on your tailored resume that match it best.
                It only uses what is on your resume, and you can edit every line before you download it.
              </p>
              <button className="btn btn-primary btn-sm" onClick={write} disabled={busy !== ""}>
                {busy === "writing" ? "Writing…" : "Write cover letter"}
              </button>
              <p className="hint" style={{ marginBottom: 0 }}>Uses one interview-prep use.</p>
            </div>
          )}

          {hasLetter && (
            <>
              <div className="brief rp-why">
                Check every line before you send it. It only draws on your resume, but you are the one who signs it.
              </div>
              <article className="rp-paper cl-paper" aria-label="Cover letter">
                <label className="visually-hidden" htmlFor="cl-text">Cover letter text</label>
                <textarea
                  id="cl-text"
                  className="cl-text"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  spellCheck
                />
              </article>
              {note && <div className="brief rp-why" role="status" style={{ marginTop: 12 }}>{note}</div>}
              <div className="cl-foot">
                <button className="btn btn-ghost btn-sm" onClick={humanize} disabled={busy !== ""}>
                  {busy === "humanizing" ? "Rewriting…" : "Make it sound more human"}
                </button>
                {before !== null && (
                  <button className="btn btn-ghost btn-sm" onClick={undo} disabled={busy !== ""}>Undo</button>
                )}
                <span className="hint">{words} words{words > 400 ? ". A little long. Most letters work best under 400." : ""}</span>
                <button className="btn btn-ghost btn-sm" onClick={write} disabled={busy !== ""}>
                  {busy === "writing" ? "Writing…" : "Write a new one"}
                </button>
                <span className="hint">Each rewrite uses one interview-prep use. It keeps your facts and numbers.</span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
