"use client";

import { useEffect, useRef, useState } from "react";
import { api, Organization, OrgContent, OrgUsageStats, OrgRosterEntry, OrgBilling, OrgContact } from "@/lib/api";

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
  const [roster, setRoster] = useState<OrgRosterEntry[]>([]);
  const [billing, setBilling] = useState<OrgBilling | null>(null);
  const [contacts, setContacts] = useState<OrgContact[]>([]);
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactDesc, setContactDesc] = useState("");
  const [addingContact, setAddingContact] = useState(false);
  const [contactError, setContactError] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [rosterUploading, setRosterUploading] = useState(false);
  const [rosterResult, setRosterResult] = useState<{ added: number; updated: number; errors: string[] } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function load() {
    api<OrgContent[]>(`/orgs/${org.id}/content`).then(setContent);
    api<OrgUsageStats>(`/orgs/${org.id}/usage`).then(setStats);
    api<OrgRosterEntry[]>(`/orgs/${org.id}/roster`).then(setRoster);
    api<OrgBilling>(`/orgs/${org.id}/billing`).then(setBilling);
    api<OrgContact[]>(`/orgs/${org.id}/contacts`).then(setContacts);
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

  async function uploadRoster(file: File) {
    setRosterUploading(true);
    setRosterResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const result = await api<{ added: number; updated: number; errors: string[] }>(
        `/orgs/${org.id}/roster/upload`, { method: "POST", body: formData }
      );
      setRosterResult(result);
      load();
    } catch (err: any) {
      setRosterResult({ added: 0, updated: 0, errors: [err.message || "Upload failed."] });
    } finally {
      setRosterUploading(false);
    }
  }

  async function subscribe(plan: "starter" | "growth") {
    try {
      const { checkout_url } = await api<{ checkout_url: string }>(
        `/orgs/${org.id}/subscribe?plan=${plan}`, { method: "POST" }
      );
      window.location.href = checkout_url;
    } catch (err: any) {
      alert(err.message || "Couldn't start checkout.");
    }
  }

  async function addContact() {
    setAddingContact(true);
    setContactError("");
    try {
      await api(`/orgs/${org.id}/contacts`, {
        method: "POST",
        body: JSON.stringify({ name: contactName, email: contactEmail, description: contactDesc }),
      });
      setContactName(""); setContactEmail(""); setContactDesc("");
      load();
    } catch (err: any) {
      setContactError(err.message || "Couldn't add that contact.");
    } finally {
      setAddingContact(false);
    }
  }

  async function removeContactEntry(contactId: number) {
    await api(`/orgs/${org.id}/contacts/${contactId}`, { method: "DELETE" });
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
        <h3 style={{ marginTop: 0 }}>Billing</h3>
        {billing && (
          <>
            <p style={{ margin: 0 }}>
              Plan: <strong>{billing.plan === "none" ? "No plan yet" : billing.plan}</strong>
              {billing.plan !== "none" && <> — {billing.subscription_status}</>}
            </p>
            <p className="hint" style={{ marginTop: 4 }}>
              {billing.employees_joined} employee{billing.employees_joined === 1 ? "" : "s"} joined,
              {" "}{billing.included_seats} included in your plan.
              {billing.overage_seats > 0 && (
                <span style={{ color: "var(--danger)" }}>
                  {" "}{billing.overage_seats} over your included seats (${billing.overage_cost_usd} — reconciled manually for now, not yet auto-billed).
                </span>
              )}
            </p>
            {billing.plan === "none" && (
              <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                <button className="btn btn-primary btn-sm" onClick={() => subscribe("starter")}>
                  Starter — $199/mo (10 seats)
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => subscribe("growth")}>
                  Growth — $599/mo (50 seats)
                </button>
              </div>
            )}
          </>
        )}
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Employee roster</h3>
        <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
          Upload a CSV (columns: email, title, tenure) to pre-register expected
          hires — they won't need to hand-type their title when they join.
          Export from Workday or any HRIS.
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          style={{ display: "none" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadRoster(f); e.target.value = ""; }}
        />
        <button className="btn btn-ghost btn-sm" onClick={() => fileInputRef.current?.click()} disabled={rosterUploading}>
          {rosterUploading ? "Uploading…" : "Upload roster CSV"}
        </button>

        {rosterResult && (
          <p className="hint" style={{ marginTop: 8 }}>
            Added {rosterResult.added}, updated {rosterResult.updated}.
            {rosterResult.errors.length > 0 && ` ${rosterResult.errors.length} row(s) had issues: ${rosterResult.errors.join(" ")}`}
          </p>
        )}

        {roster.length > 0 && (
          <div style={{ marginTop: 16 }}>
            {roster.map((r) => (
              <div key={r.id} className="points-event-row">
                <div>
                  <div style={{ fontWeight: 600 }}>{r.email}</div>
                  <div className="hint">{r.title || "(no title given)"}</div>
                </div>
                <span className={`pill ${r.joined ? "pill-approved" : "pill-default"}`}>
                  {r.joined ? "Joined" : "Not yet joined"}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Human contacts</h3>
        <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
          Real people at your company for things AI can't do directly — an office
          tour, a face-to-face intro. Job Buddy will naturally mention them, and
          employees can request an actual handoff (a real email gets sent, containing
          only what the employee chooses to write — never their chat history).
        </p>

        {contacts.map((c) => (
          <div key={c.id} className="points-event-row">
            <div>
              <div style={{ fontWeight: 600 }}>{c.name} — {c.email}</div>
              <div className="hint">{c.description || "(no description)"}</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => removeContactEntry(c.id)}>Remove</button>
          </div>
        ))}

        <div style={{ marginTop: contacts.length > 0 ? 16 : 0 }}>
          <div className="field">
            <label>Name</label>
            <input value={contactName} onChange={(e) => setContactName(e.target.value)} placeholder="e.g. Sarah Chen" />
          </div>
          <div className="field">
            <label>Email</label>
            <input value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} placeholder="sarah@acme.com" />
          </div>
          <div className="field">
            <label>What they help with</label>
            <input value={contactDesc} onChange={(e) => setContactDesc(e.target.value)} placeholder="e.g. Office tours & facilities" />
          </div>
          {contactError && <p className="error-text">{contactError}</p>}
          <button className="btn btn-primary btn-sm" onClick={addContact}
                  disabled={addingContact || !contactName.trim() || !contactEmail.trim()}>
            {addingContact ? "Adding…" : "Add contact"}
          </button>
        </div>
      </div>

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
