"use client";

import { useEffect, useState } from "react";
import { api, SearchProfile } from "@/lib/api";

const EMPTY: Omit<SearchProfile, "id"> = {
  name: "",
  titles: [],
  locations: [],
  seniority: [],
  min_match_score: 60,
  exclude_companies: [],
  keywords_required: [],
  keywords_excluded: [],
  active: true,
};

export default function ProfilesPage() {
  const [profiles, setProfiles] = useState<SearchProfile[]>([]);
  const [editing, setEditing] = useState<SearchProfile | (typeof EMPTY) | null>(null);
  const [error, setError] = useState("");
  // Raw text for each comma-separated field, kept SEPARATE from the
  // parsed array in `editing`. The input's displayed value comes from
  // here, never from editing.titles.join(", ") etc. -- deriving the
  // displayed value straight from the array meant typing a trailing
  // "," or a space got silently discarded every keystroke: splitList
  // trims and drops empty entries, so "Chicago," briefly became the
  // array ["Chicago"], which then re-rendered the input back down to
  // "Chicago" -- the comma (or a bare trailing space) never had a
  // chance to persist, so it looked like those keys just didn't work.
  // Parsing into the actual array still happens on every change (see
  // each input's onChange below), just without feeding back into what
  // the input visibly shows until the user's done typing that token.
  const [titlesText, setTitlesText] = useState("");
  const [locationsText, setLocationsText] = useState("");
  const [seniorityText, setSeniorityText] = useState("");
  const [excludeCompaniesText, setExcludeCompaniesText] = useState("");

  function startEditing(p: SearchProfile | (typeof EMPTY)) {
    setEditing(p);
    setTitlesText(p.titles.join(", "));
    setLocationsText(p.locations.join(", "));
    setSeniorityText(p.seniority.join(", "));
    setExcludeCompaniesText(p.exclude_companies.join(", "));
  }

  async function load() {
    setProfiles(await api<SearchProfile[]>("/profiles"));
  }

  useEffect(() => { load(); }, []);

  async function save() {
    if (!editing) return;
    setError("");
    try {
      if ("id" in editing) {
        await api(`/profiles/${editing.id}`, { method: "PUT", body: JSON.stringify(editing) });
      } else {
        await api("/profiles", { method: "POST", body: JSON.stringify(editing) });
      }
      setEditing(null);
      load();
    } catch (err: any) {
      setError(err.message || "Couldn't save this profile.");
    }
  }

  async function remove(id: number) {
    if (!confirm("Delete this search profile?")) return;
    await api(`/profiles/${id}`, { method: "DELETE" });
    load();
  }

  return (
    <div>
      <div className="topbar">
        <h1>Search profiles</h1>
        <button className="btn btn-primary" onClick={() => startEditing({ ...EMPTY })}>
          + New profile
        </button>
      </div>
      <p className="muted">
        Every profile you add runs at the same time. A job gets queued under
        whichever profile it matches best, as long as it clears that
        profile's match threshold.
      </p>

      {profiles.length === 0 && !editing && (
        <div className="empty-state">
          No search profiles yet. Add one to start finding matches — e.g.
          "AI Security Engineer" and "ML Security Engineer" can both run at once.
        </div>
      )}

      {profiles.map((p) => (
        <div key={p.id} className="card">
          <div className="card-row">
            <div>
              <h3>{p.name} {!p.active && <span className="pill pill-default">Paused</span>}</h3>
              <div className="profile-tags">
                {p.titles.map((t) => <span key={t} className="tag">{t}</span>)}
              </div>
              <p className="muted" style={{ marginTop: 8, fontSize: "0.85rem" }}>
                {p.locations.join(", ") || "Any location"} · min match {p.min_match_score}%
              </p>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => startEditing(p)}>Edit</button>
              <button className="btn btn-danger-ghost btn-sm" onClick={() => remove(p.id)}>Delete</button>
            </div>
          </div>
        </div>
      ))}

      {editing && (
        <div className="card" style={{ borderColor: "var(--accent)" }}>
          <h3>{"id" in editing ? "Edit profile" : "New profile"}</h3>

          <div className="field">
            <label>Profile name</label>
            <input value={editing.name}
                   onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                   placeholder="e.g. AI Security Engineer" />
          </div>

          <div className="field">
            <label>Job titles to match (comma-separated)</label>
            <input value={titlesText}
                   onChange={(e) => { setTitlesText(e.target.value); setEditing({ ...editing, titles: splitList(e.target.value) }); }}
                   placeholder="AI Security Engineer, ML Security Engineer" />
            <p className="hint">
              Doesn't need to be an exact title match — matching is done by an AI reading the
              full job description against your resume, not string-matching these words.
            </p>
          </div>

          <div className="field">
            <label>Locations (comma-separated, blank = anywhere)</label>
            <input value={locationsText}
                   onChange={(e) => { setLocationsText(e.target.value); setEditing({ ...editing, locations: splitList(e.target.value) }); }}
                   placeholder="Remote" />
            <p className="hint">
              This filters strictly — a job outside every location listed here won't match,
              regardless of how good the title fit is. Add "Remote" too if you're open to it;
              a lot of what gets discovered skews remote.
            </p>
          </div>

          <div className="field">
            <label>Seniority (comma-separated)</label>
            <input value={seniorityText}
                   onChange={(e) => { setSeniorityText(e.target.value); setEditing({ ...editing, seniority: splitList(e.target.value) }); }}
                   placeholder="Mid, Senior" />
          </div>

          <div className="field">
            <label>Minimum match score ({editing.min_match_score}%)</label>
            <input type="range" min={0} max={100} value={editing.min_match_score}
                   onChange={(e) => setEditing({ ...editing, min_match_score: Number(e.target.value) })} />
            <p className="hint">
              How good a fit a job needs to be before it becomes an application you review.
              Higher = fewer, more targeted matches; lower = more matches, including looser
              fits. 50-60% is a reasonable starting point — if you're getting nothing, this is
              usually the first thing to lower, especially combined with a narrow location list.
            </p>
          </div>

          <div className="field">
            <label>Exclude companies (comma-separated)</label>
            <input value={excludeCompaniesText}
                   onChange={(e) => { setExcludeCompaniesText(e.target.value); setEditing({ ...editing, exclude_companies: splitList(e.target.value) }); }} />
          </div>

          <div className="field">
            <label>
              <input type="checkbox" checked={editing.active} style={{ width: "auto", marginRight: 8 }}
                     onChange={(e) => setEditing({ ...editing, active: e.target.checked })} />
              Active
            </label>
          </div>

          {error && <p className="error-text">{error}</p>}

          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary" onClick={save}>Save profile</button>
            <button className="btn btn-ghost" onClick={() => { setEditing(null); setError(""); }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}

function splitList(value: string): string[] {
  return value.split(",").map((s) => s.trim()).filter(Boolean);
}
