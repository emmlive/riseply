"use client";

import { useEffect, useRef, useState } from "react";
import { api, StudyFolder, StudyNote, StudyNoteSource } from "@/lib/api";

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
          title: title.trim(), content: draft.content, folder_id: folderId, session_id: draft.sessionId,
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

              <p className="sf-preview" aria-label="What will be saved">{draft.content.slice(0, 260)}{draft.content.length > 260 ? "…" : ""}</p>

              <div className="sf-actions">
                <button className="btn btn-primary btn-sm" onClick={save} disabled={saving || folders === null}>
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
