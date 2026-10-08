"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, formatWhen, StudyFolder, StudyNote } from "@/lib/api";

type Selection = "all" | "unfiled" | number;

export default function StudyFoldersPage() {
  const [folders, setFolders] = useState<StudyFolder[]>([]);
  const [notes, setNotes] = useState<StudyNote[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Selection>("all");
  const [query, setQuery] = useState("");

  const [addingFolder, setAddingFolder] = useState(false);
  const [folderName, setFolderName] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");

  const [editingId, setEditingId] = useState<number | "new" | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [copiedId, setCopiedId] = useState<number | null>(null);

  async function load() {
    try {
      const [f, n] = await Promise.all([
        api<StudyFolder[]>("/career-coach/study/folders"),
        api<StudyNote[]>("/career-coach/study/notes"),
      ]);
      setFolders(f);
      setNotes(n);
    } catch (e: any) {
      setError(e?.message || "We couldn't load your study folders. Please refresh the page.");
    } finally {
      setLoaded(true);
    }
  }
  useEffect(() => { load(); }, []);

  const counts = useMemo(() => {
    const byFolder: Record<number, number> = {};
    let unfiled = 0;
    for (const n of notes) {
      if (n.folder_id === null) unfiled += 1;
      else byFolder[n.folder_id] = (byFolder[n.folder_id] || 0) + 1;
    }
    return { byFolder, unfiled };
  }, [notes]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return notes.filter((n) => {
      if (selected === "unfiled" && n.folder_id !== null) return false;
      if (typeof selected === "number" && n.folder_id !== selected) return false;
      return !q || n.title.toLowerCase().includes(q) || n.content.toLowerCase().includes(q);
    });
  }, [notes, selected, query]);

  const currentFolder = typeof selected === "number" ? folders.find((f) => f.id === selected) : undefined;
  const folderName_ = (id: number | null) => (id === null ? "Unfiled" : folders.find((f) => f.id === id)?.name || "Unfiled");

  async function run<T>(fn: () => Promise<T>, fallback: string): Promise<T | undefined> {
    setBusy(true);
    setError("");
    try {
      return await fn();
    } catch (e: any) {
      setError(e?.message || fallback);
    } finally {
      setBusy(false);
    }
  }

  async function createFolder() {
    const name = folderName.trim();
    if (!name) return;
    const f = await run(() => api<StudyFolder>("/career-coach/study/folders", { method: "POST", body: JSON.stringify({ name }) }),
      "We couldn't create that folder.");
    if (f) {
      setFolders((list) => [...list, f].sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase())));
      setSelected(f.id);
      setFolderName("");
      setAddingFolder(false);
    }
  }

  async function renameFolder() {
    if (!currentFolder || !renameValue.trim()) return;
    const f = await run(() => api<StudyFolder>(`/career-coach/study/folders/${currentFolder.id}`, {
      method: "PATCH", body: JSON.stringify({ name: renameValue.trim() }),
    }), "We couldn't rename that folder.");
    if (f) {
      setFolders((list) => list.map((x) => (x.id === f.id ? f : x)).sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase())));
      setRenaming(false);
    }
  }

  async function deleteFolder() {
    if (!currentFolder) return;
    if (!window.confirm(`Delete the folder "${currentFolder.name}"? Its notes aren't deleted. They move to Unfiled.`)) return;
    const id = currentFolder.id;
    const ok = await run(async () => { await api(`/career-coach/study/folders/${id}`, { method: "DELETE" }); return true; },
      "We couldn't delete that folder.");
    if (ok) {
      setFolders((list) => list.filter((f) => f.id !== id));
      setNotes((list) => list.map((n) => (n.folder_id === id ? { ...n, folder_id: null } : n)));
      setSelected("unfiled");
    }
  }

  function startEdit(n: StudyNote) {
    setEditingId(n.id);
    setEditTitle(n.title);
    setEditContent(n.content);
  }

  function startNew() {
    setEditingId("new");
    setEditTitle("");
    setEditContent("");
  }

  async function saveEdit() {
    if (editingId === null || !editContent.trim()) { setError("A note needs some text."); return; }
    if (editingId === "new") {
      const note = await run(() => api<StudyNote>("/career-coach/study/notes", {
        method: "POST",
        body: JSON.stringify({ title: editTitle.trim(), content: editContent, source: "manual", folder_id: typeof selected === "number" ? selected : null }),
      }), "We couldn't save that note.");
      if (note) { setNotes((list) => [note, ...list]); setEditingId(null); }
      return;
    }
    const id = editingId;
    const note = await run(() => api<StudyNote>(`/career-coach/study/notes/${id}`, {
      method: "PATCH", body: JSON.stringify({ title: editTitle.trim(), content: editContent }),
    }), "We couldn't save your changes.");
    if (note) { setNotes((list) => list.map((n) => (n.id === note.id ? note : n))); setEditingId(null); }
  }

  async function moveNote(n: StudyNote, value: string) {
    const folder_id = value === "" ? null : Number(value);
    const note = await run(() => api<StudyNote>(`/career-coach/study/notes/${n.id}`, {
      method: "PATCH", body: JSON.stringify({ folder_id }),
    }), "We couldn't move that note.");
    if (note) setNotes((list) => list.map((x) => (x.id === note.id ? note : x)));
  }

  async function deleteNote(n: StudyNote) {
    if (!window.confirm("Delete this note? This can't be undone.")) return;
    const ok = await run(async () => { await api(`/career-coach/study/notes/${n.id}`, { method: "DELETE" }); return true; },
      "We couldn't delete that note.");
    if (ok) setNotes((list) => list.filter((x) => x.id !== n.id));
  }

  async function copyNote(n: StudyNote) {
    try {
      await navigator.clipboard.writeText(`${n.title}\n\n${n.content}`);
      setCopiedId(n.id);
      setTimeout(() => setCopiedId((cur) => (cur === n.id ? null : cur)), 1800);
    } catch {
      setError("Your browser wouldn't let us copy that. Select the text and copy it instead.");
    }
  }

  const heading = selected === "all" ? "All notes" : selected === "unfiled" ? "Unfiled" : currentFolder?.name || "Folder";

  const editor = (
    <div className="card st-editor">
      <label className="cc-label" htmlFor="st-title">Title</label>
      <input id="st-title" className="cc-input" value={editTitle} maxLength={160}
             onChange={(e) => setEditTitle(e.target.value)} placeholder="What is this about?" />
      <label className="cc-label" htmlFor="st-content" style={{ marginTop: 12 }}>Note</label>
      <textarea id="st-content" className="cc-input" value={editContent} maxLength={20000} style={{ minHeight: 160 }}
                onChange={(e) => setEditContent(e.target.value)} placeholder="Takeaways, answers worth reusing, things to study…" />
      <div className="st-actions">
        <button className="btn btn-primary btn-sm" onClick={saveEdit} disabled={busy || !editContent.trim()}>
          {busy ? "Saving…" : "Save note"}
        </button>
        <button className="btn btn-ghost btn-sm" onClick={() => setEditingId(null)} disabled={busy}>Cancel</button>
      </div>
    </div>
  );

  return (
    <div>
      <div className="cc-head">
        <h1>Study folders</h1>
        <p>
          Notes, coach replies and feedback you&apos;ve saved from the <Link href="/dashboard/career-coach">Career Coach</Link>,
          organised your way. Only you can see them, and the coach never reads them.
        </p>
      </div>

      {error && <div className="cc-error" role="alert">{error}</div>}

      <div className="st-grid">
        <nav className="card st-folders" aria-label="Study folders">
          <button className={`st-folder ${selected === "all" ? "is-active" : ""}`} onClick={() => setSelected("all")}>
            <span>All notes</span><span className="st-count">{notes.length}</span>
          </button>
          <button className={`st-folder ${selected === "unfiled" ? "is-active" : ""}`} onClick={() => setSelected("unfiled")}>
            <span>Unfiled</span><span className="st-count">{counts.unfiled}</span>
          </button>
          {folders.map((f) => (
            <button key={f.id} className={`st-folder ${selected === f.id ? "is-active" : ""}`} onClick={() => { setSelected(f.id); setRenaming(false); }}>
              <span className="st-folder-name">{f.name}</span><span className="st-count">{counts.byFolder[f.id] || 0}</span>
            </button>
          ))}
          {addingFolder ? (
            <div className="st-newfolder">
              <input className="cc-input" autoFocus value={folderName} maxLength={60} aria-label="New folder name"
                     placeholder="Folder name" onChange={(e) => setFolderName(e.target.value)}
                     onKeyDown={(e) => { if (e.key === "Enter") createFolder(); if (e.key === "Escape") setAddingFolder(false); }} />
              <div className="st-actions">
                <button className="btn btn-primary btn-sm" onClick={createFolder} disabled={busy || !folderName.trim()}>Create</button>
                <button className="btn btn-ghost btn-sm" onClick={() => { setAddingFolder(false); setFolderName(""); }}>Cancel</button>
              </div>
            </div>
          ) : (
            <button className="btn btn-ghost btn-sm st-add" onClick={() => setAddingFolder(true)}>+ New folder</button>
          )}
        </nav>

        <section className="st-main" aria-label={heading}>
          <div className="st-toolbar">
            {renaming && currentFolder ? (
              <div className="st-rename">
                <input className="cc-input" autoFocus value={renameValue} maxLength={60} aria-label="Folder name"
                       onChange={(e) => setRenameValue(e.target.value)}
                       onKeyDown={(e) => { if (e.key === "Enter") renameFolder(); if (e.key === "Escape") setRenaming(false); }} />
                <button className="btn btn-primary btn-sm" onClick={renameFolder} disabled={busy || !renameValue.trim()}>Save</button>
                <button className="btn btn-ghost btn-sm" onClick={() => setRenaming(false)}>Cancel</button>
              </div>
            ) : (
              <h2 className="st-title">{heading}</h2>
            )}
            <div className="st-toolbar-actions">
              {currentFolder && !renaming && (
                <>
                  <button className="btn btn-ghost btn-sm" onClick={() => { setRenameValue(currentFolder.name); setRenaming(true); }}>Rename</button>
                  <button className="btn btn-ghost btn-sm" onClick={deleteFolder} disabled={busy}>Delete folder</button>
                </>
              )}
              <button className="btn btn-primary btn-sm" onClick={startNew} disabled={editingId !== null}>+ New note</button>
            </div>
          </div>

          <input className="cc-input st-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)}
                 placeholder="Search your notes" aria-label="Search notes" />

          {editingId === "new" && editor}

          {!loaded ? (
            <p className="cc-empty">Loading…</p>
          ) : visible.length === 0 && editingId !== "new" ? (
            <div className="card st-empty">
              <p>
                {notes.length === 0
                  ? "Nothing saved yet. In a Career Coach session, use “Save to study folder” on your notepad, a coach reply or your feedback."
                  : query
                    ? "No notes match your search."
                    : "No notes in this folder yet."}
              </p>
              {notes.length === 0 && <Link className="btn btn-primary btn-sm" href="/dashboard/career-coach">Go to Career Coach</Link>}
            </div>
          ) : (
            visible.map((n) => (
              editingId === n.id ? <div key={n.id}>{editor}</div> : (
                <article key={n.id} className="card st-note">
                  <header className="st-note-head">
                    <div>
                      <h3 className="st-note-title">{n.title || "Untitled note"}</h3>
                      <p className="hint st-note-meta">
                        {[n.source_label, `Saved ${formatWhen(n.created_at)}`, selected === "all" ? folderName_(n.folder_id) : ""].filter(Boolean).join(" · ")}
                      </p>
                    </div>
                  </header>
                  <p className={`st-note-body ${expanded[n.id] ? "" : "is-clamped"}`}>{n.content}</p>
                  {(n.content.length > 320 || n.content.split("\n").length > 6) && (
                    <button className="st-more" onClick={() => setExpanded((e) => ({ ...e, [n.id]: !e[n.id] }))}>
                      {expanded[n.id] ? "Show less" : "Show more"}
                    </button>
                  )}
                  <div className="st-actions">
                    <button className="btn btn-ghost btn-sm" onClick={() => startEdit(n)} disabled={editingId !== null}>Edit</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => copyNote(n)}>{copiedId === n.id ? "Copied" : "Copy"}</button>
                    <label className="st-move">
                      <span className="hint">Move to</span>
                      <select className="cc-input" value={n.folder_id === null ? "" : String(n.folder_id)}
                              onChange={(e) => moveNote(n, e.target.value)} aria-label={`Move “${n.title || "note"}” to a folder`}>
                        <option value="">Unfiled</option>
                        {folders.map((f) => <option key={f.id} value={String(f.id)}>{f.name}</option>)}
                      </select>
                    </label>
                    <button className="btn btn-ghost btn-sm st-delete" onClick={() => deleteNote(n)} disabled={busy}>Delete</button>
                  </div>
                </article>
              )
            ))
          )}
        </section>
      </div>
    </div>
  );
}
