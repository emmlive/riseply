"use client";

import { useEffect, useState } from "react";
import { api, LibraryItem, LibraryItemInput, LibraryResourceType, User } from "@/lib/api";
import ResourceCard from "@/components/ResourceCard";

// The Library: curated learning resources. Everyone can browse and
// search; the Career Coach recommends from this same list. Platform
// admins also get inline add / hide / delete controls here (rather than a
// separate admin tab) since the list is small and curated by hand.

const TYPES: LibraryResourceType[] = ["course", "article", "video", "book", "practice", "reference", "tool"];

const BLANK: LibraryItemInput = {
  title: "", url: "https://", description: "", resource_type: "course",
  fields: [], level: "all", cost: "free", active: true,
};

export default function LibraryPage() {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [freeOnly, setFreeOnly] = useState(false);

  const [editing, setEditing] = useState<{ id: number | null; draft: LibraryItemInput; fieldsText: string } | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api<User>("/me").then((u) => setIsAdmin(!!u.is_admin)).catch(() => {});
  }, []);

  useEffect(() => {
    // Debounce typing in the search box.
    const t = setTimeout(async () => {
      const params = new URLSearchParams();
      if (q.trim()) params.set("q", q.trim());
      if (type) params.set("resource_type", type);
      if (freeOnly) params.set("cost", "free");
      if (isAdmin) params.set("include_inactive", "true");
      try {
        setItems(await api<LibraryItem[]>(`/library/items?${params.toString()}`));
        setError("");
      } catch (err: any) {
        setError(err.message || "Couldn't load the Library.");
      } finally {
        setLoaded(true);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [q, type, freeOnly, isAdmin]);

  function startEdit(item?: LibraryItem) {
    if (item) {
      const { id, ...rest } = item;
      setEditing({ id, draft: rest, fieldsText: item.fields.join(", ") });
    } else {
      setEditing({ id: null, draft: { ...BLANK }, fieldsText: "" });
    }
  }

  async function save() {
    if (!editing || saving) return;
    setSaving(true);
    setError("");
    const body = {
      ...editing.draft,
      fields: editing.fieldsText.split(",").map((f) => f.trim()).filter(Boolean),
    };
    try {
      const saved = await api<LibraryItem>(
        editing.id === null ? "/library/items" : `/library/items/${editing.id}`,
        { method: editing.id === null ? "POST" : "PUT", body: JSON.stringify(body) }
      );
      setItems((rows) =>
        editing.id === null
          ? [...rows, saved].sort((a, b) => a.title.localeCompare(b.title))
          : rows.map((r) => (r.id === saved.id ? saved : r))
      );
      setEditing(null);
    } catch (err: any) {
      setError(err.message || "Couldn't save that item.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(item: LibraryItem) {
    if (!confirm(`Delete "${item.title}" from the Library? The coach will stop recommending it.`)) return;
    try {
      await api(`/library/items/${item.id}`, { method: "DELETE" });
      setItems((rows) => rows.filter((r) => r.id !== item.id));
    } catch (err: any) {
      setError(err.message || "Couldn't delete that item.");
    }
  }

  async function toggleActive(item: LibraryItem) {
    const { id, ...rest } = item;
    try {
      const saved = await api<LibraryItem>(`/library/items/${id}`, {
        method: "PUT", body: JSON.stringify({ ...rest, active: !item.active }),
      });
      setItems((rows) => rows.map((r) => (r.id === saved.id ? saved : r)));
    } catch (err: any) {
      setError(err.message || "Couldn't update that item.");
    }
  }

  const set = <K extends keyof LibraryItemInput>(k: K, v: LibraryItemInput[K]) =>
    setEditing((e) => (e ? { ...e, draft: { ...e.draft, [k]: v } } : e));

  return (
    <div>
      <h1>Library</h1>
      <p className="hint">
        Hand-picked resources for going deeper on a skill or field. Your Career Coach recommends from
        this list when it spots something worth studying, and only from this list.
      </p>

      {error && <div className="card" style={{ borderColor: "var(--danger, #c0392b)" }}>{error}</div>}

      <div className="card">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input
            placeholder="Search by topic, skill, or title (e.g. SQL, UX, security)"
            value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: "1 1 240px" }}
          />
          <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Resource type">
            <option value="">All types</option>
            {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <input type="checkbox" checked={freeOnly} onChange={(e) => setFreeOnly(e.target.checked)} /> Free only
          </label>
          {isAdmin && <button className="btn btn-primary btn-sm" onClick={() => startEdit()}>Add resource</button>}
        </div>
      </div>

      {editing && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>{editing.id === null ? "Add a resource" : "Edit resource"}</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <input placeholder="Title" value={editing.draft.title} maxLength={200} onChange={(e) => set("title", e.target.value)} />
            <input placeholder="https://…" value={editing.draft.url} maxLength={500} onChange={(e) => set("url", e.target.value)} />
            <textarea placeholder="One or two sentences on what it covers and who it's for" value={editing.draft.description}
                      maxLength={1000} onChange={(e) => set("description", e.target.value)} />
            <input placeholder="Topics, comma-separated (e.g. sql, data analysis)" value={editing.fieldsText}
                   onChange={(e) => setEditing((x) => (x ? { ...x, fieldsText: e.target.value } : x))} />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <select value={editing.draft.resource_type} onChange={(e) => set("resource_type", e.target.value as LibraryResourceType)}>
                {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <select value={editing.draft.level} onChange={(e) => set("level", e.target.value as LibraryItem["level"])}>
                {["all", "beginner", "intermediate", "advanced"].map((l) => <option key={l} value={l}>{l} level</option>)}
              </select>
              <select value={editing.draft.cost} onChange={(e) => set("cost", e.target.value as LibraryItem["cost"])}>
                {["free", "freemium", "paid"].map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <input type="checkbox" checked={editing.draft.active} onChange={(e) => set("active", e.target.checked)} /> Visible
              </label>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-primary btn-sm" onClick={save} disabled={saving || editing.draft.title.trim().length < 2}>
                {saving ? "Saving…" : "Save"}
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => setEditing(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {loaded && items.length === 0 && (
        <p className="hint">Nothing matches that search yet. Try a broader topic.</p>
      )}

      {items.map((item) => (
        <div key={item.id} style={{ opacity: item.active ? 1 : 0.55 }}>
          <ResourceCard item={item} />
          {isAdmin && (
            <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
              {!item.active && <span className="hint">Hidden from learners and the coach</span>}
              <button className="btn btn-ghost btn-sm" onClick={() => startEdit(item)}>Edit</button>
              <button className="btn btn-ghost btn-sm" onClick={() => toggleActive(item)}>{item.active ? "Hide" : "Show"}</button>
              <button className="btn btn-danger-ghost btn-sm" onClick={() => remove(item)}>Delete</button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
