"use client";

import { useEffect, useState } from "react";
import { api, Organization, Department, InternalJobPosting, InternalJobApplication } from "@/lib/api";

// Internal mobility -- an org posts its OWN open roles, employees apply
// with the resume already on file. Deliberately separate from the
// external, AI-matched job discovery system (Search profiles/Resume/
// Applications/Rise Index): those exist to help someone find a job
// somewhere else; this exists to help someone move within the same
// company, without ever leaving the org's own admin/employee context.
// Same outer/inner org-selection pattern as Org Buddy and Mentor as a
// Service -- see those pages for why (no "create an organization" UI
// needed here, an org must already exist).

export default function InternalJobsPage() {
  const [orgs, setOrgs] = useState<Organization[] | null>(null);
  const [selected, setSelected] = useState<Organization | null>(null);

  useEffect(() => {
    api<Organization[]>("/orgs/mine").then((orgList) => {
      setOrgs(orgList);
      if (orgList.length > 0 && !selected) setSelected(orgList[0]);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (orgs === null) return <p className="muted">Loading…</p>;

  if (orgs.length === 0) {
    return (
      <div>
        <h1>Internal Jobs</h1>
        <p className="muted">
          You'll need an organization set up first — head to Org Buddy to create one, then come
          back here to post internal openings.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="topbar">
        <h1>Internal Jobs</h1>
        {orgs.length > 1 && (
          <select
            value={selected?.id ?? ""}
            onChange={(e) => setSelected(orgs.find((o) => o.id === Number(e.target.value)) || null)}
            style={{ width: 220 }}
          >
            {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        )}
      </div>
      <p className="muted">
        Internal mobility — post an opening at your own organization and let employees apply with
        the resume already on file, right from Job Buddy. Separate from external job search:
        this keeps people growing within your company instead of looking elsewhere.
      </p>
      {selected && <InternalJobsDashboard org={selected} />}
    </div>
  );
}

function InternalJobsDashboard({ org }: { org: Organization }) {
  const [postings, setPostings] = useState<InternalJobPosting[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [showNewForm, setShowNewForm] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDepartmentId, setNewDepartmentId] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [applicantsOpenFor, setApplicantsOpenFor] = useState<number | null>(null);
  const [applicants, setApplicants] = useState<Record<number, InternalJobApplication[]>>({});

  function load() {
    api<InternalJobPosting[]>(`/orgs/${org.id}/internal-jobs`).then(setPostings).catch(() => {});
    api<Department[]>(`/orgs/${org.id}/departments`).then(setDepartments).catch(() => {});
  }

  useEffect(() => { load(); }, [org.id]);

  async function createPosting() {
    if (!newTitle.trim()) return;
    setCreating(true);
    try {
      await api(`/orgs/${org.id}/internal-jobs`, {
        method: "POST",
        body: JSON.stringify({
          title: newTitle,
          department_id: newDepartmentId ? Number(newDepartmentId) : null,
          description: newDescription,
        }),
      });
      setShowNewForm(false);
      setNewTitle(""); setNewDepartmentId(""); setNewDescription("");
      load();
    } catch (err: any) {
      alert(err.message || "Couldn't create that posting.");
    } finally {
      setCreating(false);
    }
  }

  async function closePosting(postingId: number) {
    if (!confirm("Close this posting? Employees won't be able to apply anymore.")) return;
    try {
      await api(`/orgs/${org.id}/internal-jobs/${postingId}/close`, { method: "POST" });
      load();
    } catch (err: any) {
      alert(err.message || "Couldn't close that posting.");
    }
  }

  async function toggleApplicants(postingId: number) {
    if (applicantsOpenFor === postingId) {
      setApplicantsOpenFor(null);
      return;
    }
    setApplicantsOpenFor(postingId);
    try {
      const rows = await api<InternalJobApplication[]>(`/orgs/${org.id}/internal-jobs/${postingId}/applicants`);
      setApplicants((prev) => ({ ...prev, [postingId]: rows }));
    } catch (err: any) {
      alert(err.message || "Couldn't load applicants.");
    }
  }

  return (
    <div className="card">
      <div className="card-row">
        <h3 style={{ marginTop: 0 }}>Postings</h3>
        <button className="btn btn-primary btn-sm" onClick={() => setShowNewForm(!showNewForm)}>
          {showNewForm ? "Cancel" : "+ New posting"}
        </button>
      </div>

      {showNewForm && (
        <div style={{ padding: 12, border: "1px solid var(--border, #eee)", borderRadius: 6, marginBottom: 12 }}>
          <div className="field">
            <label>Title</label>
            <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="e.g. Senior ICU Nurse" />
          </div>
          <div className="field">
            <label>Department (optional)</label>
            <select value={newDepartmentId} onChange={(e) => setNewDepartmentId(e.target.value)}>
              <option value="">Company-wide</option>
              {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Description</label>
            <textarea value={newDescription} onChange={(e) => setNewDescription(e.target.value)} rows={3} />
          </div>
          <button className="btn btn-primary btn-sm" disabled={creating || !newTitle.trim()} onClick={createPosting}>
            {creating ? "Posting…" : "Post opening"}
          </button>
        </div>
      )}

      {postings.length === 0 ? (
        <div className="empty-state" style={{ marginTop: 8 }}>
          No internal postings yet — once you post one, employees will see it right on their
          Job Buddy page and can apply with the resume already on file.
        </div>
      ) : (
        postings.map((p) => (
          <div key={p.id} style={{ padding: "10px 0", borderBottom: "1px solid var(--border, #eee)" }}>
            <div className="card-row">
              <div>
                <div style={{ fontWeight: 600 }}>
                  {p.title}
                  {p.department_name && <span className="hint"> · {p.department_name}</span>}
                  {p.closed_at && <span className="pill" style={{ marginLeft: 8, fontSize: "0.72rem" }}>Closed</span>}
                </div>
                {p.description && <div className="hint" style={{ marginTop: 4 }}>{p.description}</div>}
              </div>
              <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                <button className="btn btn-ghost btn-sm" onClick={() => toggleApplicants(p.id)}>
                  {applicantsOpenFor === p.id ? "Hide" : `Applicants (${p.applicant_count})`}
                </button>
                {!p.closed_at && (
                  <button className="btn btn-ghost btn-sm" onClick={() => closePosting(p.id)}>Close</button>
                )}
              </div>
            </div>
            {applicantsOpenFor === p.id && (
              <div style={{ marginTop: 8, marginLeft: 12 }}>
                {(applicants[p.id] || []).length === 0 ? (
                  <p className="hint">No applicants yet.</p>
                ) : (
                  (applicants[p.id] || []).map((a) => (
                    <div key={a.id} style={{ padding: "6px 0", borderBottom: "1px solid var(--border, #eee)" }}>
                      <div style={{ fontWeight: 600 }}>{a.applicant_name} <span className="hint">· {a.applicant_email}</span></div>
                      {a.note && <div className="hint">{a.note}</div>}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
}
