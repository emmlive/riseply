"use client";

import { useEffect, useState } from "react";
import { api, Organization, OrgContent, OrgUsageStats } from "@/lib/api";

export default function OrgBuddyPage() {
  const [orgs, setOrgs] = useState<Organization[] | null>(null);
  const [selected, setSelected] = useState<Organization | null>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  function load() {
    api<Organization[]>("/orgs/mine").then((orgList) => {
      setOrgs(orgList);
      if (orgList.length > 0 && !selected) setSelected(orgList[0]);
    });
  }

  useEffect(() => { load(); }, []);

  async function createOrg() {
    setCreating(true);
    setError("");
    try {
      const org = await api<Organization>("/orgs", { method: "POST", body: JSON.stringify({ name }) });
      setName("");
      load();
      setSelected(org);
    } catch (err: any) {
      setError(err.message || "Couldn't create the organization.");
    } finally {
      setCreating(false);
    }
  }

  if (orgs === null) return <p className="muted">Loading…</p>;

  return (
    <div>
      <h1>Org Buddy</h1>
      <p className="muted">
        Your company's own onboarding buddy — the traditional practice of
        pairing new hires with support for their first stretch, grounded
        in your actual handbook, culture, and team info instead of
        generic advice. Employee conversations stay private; you see
        that it's working, not what anyone said.
      </p>

      {orgs.length === 0 && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Set up your organization</h3>
          <div className="field">
            <label>Company name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          {error && <p className="error-text">{error}</p>}
          <button className="btn btn-primary btn-sm" onClick={createOrg} disabled={creating || !name.trim()}>
            {creating ? "Creating…" : "Create organization"}
          </button>
        </div>
      )}

      {orgs.length > 0 && selected && (
        <OrgDashboard org={selected} orgs={orgs} onSwitch={setSelected} />
      )}
    </div>
  );
}

function OrgDashboard({ org, orgs, onSwitch }: { org: Organization; orgs: Organization[]; onSwitch: (o: Organization) => void }) {
  const [content, setContent] = useState<OrgContent[]>([]);
  const [stats, setStats] = useState<OrgUsageStats | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  function load() {
    api<OrgContent[]>(`/orgs/${org.id}/content`).then(setContent);
    api<OrgUsageStats>(`/orgs/${org.id}/usage`).then(setStats);
  }

  useEffect(() => { load(); }, [org.id]);

  async function addContent() {
    setAdding(true);
    setError("");
    try {
      await api(`/orgs/${org.id}/content`, { method: "POST", body: JSON.stringify({ title, content: body }) });
      setTitle(""); setBody("");
      load();
    } catch (err: any) {
      setError(err.message || "Couldn't add that content.");
    } finally {
      setAdding(false);
    }
  }

  async function removeContent(contentId: number) {
    await api(`/orgs/${org.id}/content/${contentId}`, { method: "DELETE" });
    load();
  }

  return (
    <div>
      {orgs.length > 1 && (
        <select value={org.id} onChange={(e) => onSwitch(orgs.find((o) => o.id === Number(e.target.value))!)}
                style={{ marginBottom: 16, width: "auto" }}>
          {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
      )}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>{org.name}</h3>
        <p className="muted" style={{ marginBottom: 4 }}>Join code — share this with new hires:</p>
        <span className="mono" style={{ fontSize: "1.3rem", fontWeight: 700, letterSpacing: 2 }}>{org.join_code}</span>
      </div>

      {stats && (
        <div className="rise-hero">
          <div className="rise-stat">
            <div className="value">{stats.employees_joined}</div>
            <div className="label">Employees joined</div>
          </div>
          <div className="rise-stat">
            <div className="value">{stats.plans_generated}</div>
            <div className="label">Plans generated</div>
          </div>
          <div className="rise-stat">
            <div className="value">{stats.avg_messages_per_employee}</div>
            <div className="label">Avg. messages / employee</div>
          </div>
        </div>
      )}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Custom onboarding content</h3>
        <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
          Handbook excerpts, culture notes, team/tool info — folded into every plan and chat reply for your employees.
        </p>

        {content.map((c) => (
          <div key={c.id} className="points-event-row">
            <div>
              <div style={{ fontWeight: 600 }}>{c.title}</div>
              <div className="hint">{c.content.slice(0, 100)}{c.content.length > 100 ? "…" : ""}</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => removeContent(c.id)}>Remove</button>
          </div>
        ))}

        <div style={{ marginTop: content.length > 0 ? 16 : 0 }}>
          <div className="field">
            <label>Title</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Engineering Handbook" />
          </div>
          <div className="field">
            <label>Content</label>
            <textarea rows={5} value={body} onChange={(e) => setBody(e.target.value)}
                      placeholder="Paste the relevant material here…" />
          </div>
          {error && <p className="error-text">{error}</p>}
          <button className="btn btn-primary btn-sm" onClick={addContent} disabled={adding || !title.trim() || !body.trim()}>
            {adding ? "Adding…" : "Add content"}
          </button>
        </div>
      </div>
    </div>
  );
}
