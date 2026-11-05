"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api, StudyFolder, StudyNote, StudyNoteSource } from "@/lib/api";
import { joinParts, splitParts } from "@/components/studyParts";
import "./SaveToStudy.css";

export interface StudyDraft {
  title: string;
  content: string;
  source: StudyNoteSource;
  sourceLabel: string;
  sessionId: number | null;
}

const NEW_FOLDER = "__new__";

// Small dialog for filing a piece of coaching material (the notepad, a
// coach reply, the session feedback) into a study folder.
export default function SaveToStudy({ draft, onClose, onSaved }: {
  draft: StudyDraft;
  onClose: () => void;
  onSaved?: (note: StudyNote) => void;
}) {
  const [folders, setFolders] = useState<StudyFolder[] | null>(null);
  const [choice, setChoice] = useState<string>("");       // "" = Unfiled, a folder id, or NEW_FOLDER
  const [newName, setNewName] = useState("");
  const [title, setTitle] = useState(draft.title);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<StudyNote | null>(null);
  const [error, setError] = useState("");
  const titleRef = useRef<HTMLInputElement>(null);

  // Choose what to keep: tick the pieces, then save them as they are or as a
  // short summary the person can edit.
  const parts = useMemo(() => splitParts(draft.content), [draft.content]);
  const canPick = parts.length >= 2;
  const [picked, setPicked] = useState<Set<number>>(() => new Set(parts.map((p) => p.id)));
  const [mode, setMode] = useState<"text" | "summary">("text");
  const [style, setStyle] = useState<"points" | "steps">("points");
  const [summary, setSummary] = useState("");
  const [summarizing, setSummarizing] = useState(false);
  const pickedText = canPick ? joinParts(parts, picked) : draft.content;
  const finalText = mode === "summary" ? summary.trim() : pickedText.trim();

  function toggle(id: number) {
    setPicked((cur) => { const n = new Set(cur); if (n.has(id)) n.delete(id); else n.add(id); return n; });
    setSummary("");
  }
  async function makeSummary() {
    if (pickedText.trim().length < 20) { setError("Pick at least a sentence to summarize."); return; }
    setSummarizing(true);
    setError("");
    try {
      const r = await api<{ summary: string }>("/career-coach/study/summarize", {
        method: "POST", body: JSON.stringify({ text: pickedText.slice(0, 12000), style, topic: draft.title }),
      });
      setSummary(r.summary);
    } catch (e: any) {
      setError(e?.message || "We couldn't summarize that. Please try again.");
    } finally {
      setSummarizing(false);
    }
  }

  useEffect(() => {
    api<StudyFolder[]>("/career-coach/study/folders")
      .then((f) => { setFolders(f); if (f.length === 0) setChoice(NEW_FOLDER); })
      .catch(() => setFolders([]));
    titleRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function save() {
    if (!finalText) { setError(mode === "summary" ? "Summarize first, or switch to the parts you picked." : "Pick at least one part to save."); return; }
    setSaving(true);
    setError("");
    try {
      let folderId: number | null = choice && choice !== NEW_FOLDER ? Number(choice) : null;
      if (choice === NEW_FOLDER) {
        if (!newName.trim()) { setError("Give the new folder a name."); setSaving(false); return; }
        const f = await api<StudyFolder>("/career-coach/study/folders", {
          method: "POST", body: JSON.stringify({ name: newName.trim() }),
        });
        folderId = f.id;
      }
      const note = await api<StudyNote>("/career-coach/study/notes", {
        method: "POST",
        body: JSON.stringify({
          title: title.trim(), content: finalText.slice(0, 20000), folder_id: folderId, session_id: draft.sessionId,
          source: draft.source, source_label: draft.sourceLabel,
        }),
      });
      setSaved(note);
      onSaved?.(note);
    } catch (e: any) {
      setError(e?.message || "We couldn't save that. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rp-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="rp-dialog sf-dialog" role="dialog" aria-modal="true" aria-label="Save to a study folder">
        <header className="rp-head">
          <div>
            <h2 className="rp-title">{saved ? "Saved" : "Save to a study folder"}</h2>
            <p className="hint">{saved ? "You can find it again under Study folders." : "Keep this to review later."}</p>
          </div>
        </header>
        <div className="rp-body sf-body">
          {saved ? (
            <div className="sf-actions">
              <a className="btn btn-primary btn-sm" href="/dashboard/career-coach/study">Open study folders</a>
              <button className="btn btn-ghost btn-sm" onClick={onClose}>Done</button>
            </div>
          ) : (
            <>
              {error && <p className="cc-error" role="alert">{error}</p>}
              <label className="cc-label" htmlFor="sf-title">Title</label>
              <input id="sf-title" ref={titleRef} className="cc-input" value={title} maxLength={160}
                     onChange={(e) => setTitle(e.target.value)} placeholder="What is this about?" />

              <label className="cc-label" htmlFor="sf-folder" style={{ marginTop: 14 }}>Folder</label>
              <select id="sf-folder" className="cc-input" value={choice} disabled={folders === null}
                      onChange={(e) => setChoice(e.target.value)}>
                <option value="">No folder (Unfiled)</option>
                {(folders || []).map((f) => <option key={f.id} value={String(f.id)}>{f.name}</option>)}
                <option value={NEW_FOLDER}>+ Create a new folder…</option>
              </select>
              {choice === NEW_FOLDER && (
                <input className="cc-input" style={{ marginTop: 8 }} value={newName} maxLength={60}
                       aria-label="New folder name" placeholder="Folder name, for example Threat modeling"
                       onChange={(e) => setNewName(e.target.value)} />
              )}

              {canPick && (
                <fieldset className="ss-pick">
                  <legend className="cc-label">What to save</legend>
                  <div className="ss-pick-tools">
                    <span className="hint">{picked.size} of {parts.length} picked</span>
                    <button type="button" className="sg-link" onClick={() => { setPicked(new Set(parts.map((p) => p.id))); setSummary(""); }}>All</button>
                    <button type="button" className="sg-link" onClick={() => { setPicked(new Set()); setSummary(""); }}>None</button>
                  </div>
                  <ul className="ss-list">
                    {parts.map((p) => (
                      <li key={p.id}>
                        <label className="ss-item">
                          <input type="checkbox" checked={picked.has(p.id)} onChange={() => toggle(p.id)} />
                          <span>{p.text}</span>
                        </label>
                      </li>
                    ))}
                  </ul>
                </fieldset>
              )}

              {canPick && (
                <fieldset className="ss-mode">
                  <legend className="cc-label">Save it as</legend>
                  <label className="cc-check">
                    <input type="radio" name="ss-mode" checked={mode === "text"} onChange={() => setMode("text")} />
                    The parts I picked, as written
                  </label>
                  <label className="cc-check">
                    <input type="radio" name="ss-mode" checked={mode === "summary"} onChange={() => setMode("summary")} />
                    A short summary of them
                  </label>
                  {mode === "summary" && (
                    <div className="ss-summary">
                      <div className="ss-summary-row">
                        <select className="cc-input" aria-label="Summary style" value={style}
                                onChange={(e) => { setStyle(e.target.value as "points" | "steps"); setSummary(""); }}>
                          <option value="points">Key points</option>
                          <option value="steps">Practical steps</option>
                        </select>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={makeSummary}
                                disabled={summarizing || picked.size === 0}>
                          {summarizing ? "Summarizing…" : summary ? "Summarize again" : "Summarize"}
                        </button>
                      </div>
                      {summary && (
                        <>
                          <label className="hint" htmlFor="ss-text">Edit it before you save</label>
                          <textarea id="ss-text" className="cc-input" rows={7} value={summary} maxLength={3000}
                                    onChange={(e) => setSummary(e.target.value)} />
                        </>
                      )}
                    </div>
                  )}
                </fieldset>
              )}

              {!canPick && <p className="sf-preview" aria-label="What will be saved">{draft.content.slice(0, 260)}{draft.content.length > 260 ? "…" : ""}</p>}

              <div className="sf-actions">
                <button className="btn btn-primary btn-sm" onClick={save} disabled={saving || folders === null || !finalText}>
                  {saving ? "Saving…" : "Save"}
                </button>
                <button className="btn btn-ghost btn-sm" onClick={onClose} disabled={saving}>Cancel</button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
