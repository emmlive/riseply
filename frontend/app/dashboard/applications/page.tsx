"use client";

import { useEffect, useState } from "react";
import { api, Application } from "@/lib/api";

const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "pending_approval", label: "Awaiting review" },
  { value: "approved", label: "Approved" },
  { value: "submitted", label: "Submitted" },
  { value: "rejected", label: "Rejected" },
];

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function ApplicationsPage() {
  const [apps, setApps] = useState<Application[]>([]);
  const [filter, setFilter] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  async function load(status: string) {
    const qs = status ? `?status=${status}` : "";
    setApps(await api<Application[]>(`/applications${qs}`));
  }

  useEffect(() => { load(filter); }, [filter]);

  async function act(id: number, action: "approve" | "reject") {
    setBusyId(id);
    try {
      await api(`/applications/${id}/${action}`, { method: "POST" });
      await load(filter);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <h1>Applications</h1>

      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            className="btn btn-ghost btn-sm"
            style={filter === f.value ? { background: "var(--accent-soft)", color: "var(--accent-hover)", borderColor: "var(--accent)" } : {}}
            onClick={() => setFilter(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {apps.length === 0 && (
        <div className="empty-state">Nothing here yet.</div>
      )}

      {apps.map((app) => (
        <div key={app.id} className="card">
          <div className="card-row">
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <h3 style={{ margin: 0 }}>{app.job_title} — {app.job_company}</h3>
                <StatusPill status={app.status} />
              </div>
              <p className="muted" style={{ margin: "4px 0" }}>{app.job_location}</p>
              <p style={{ margin: "8px 0", fontSize: "0.9rem" }}>{app.match_reason}</p>
              {app.notes && <p className="hint">{app.notes}</p>}
              <div style={{ display: "flex", gap: 10, marginTop: 10, fontSize: "0.85rem" }}>
                <a href={app.job_url} target="_blank" rel="noreferrer">View posting →</a>
                {app.tailored_resume_path && (
                  <a href={`${API_URL}/files/tailored_resumes/${app.tailored_resume_path.split("/").pop()}`}>
                    Download tailored resume
                  </a>
                )}
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 10 }}>
              <span className={`ticket ${app.match_score >= 80 ? "high" : ""}`}>
                match <span className="score">{app.match_score}%</span>
              </span>
              {app.status === "pending_approval" && (
                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    className="btn btn-primary btn-sm"
                    disabled={busyId === app.id}
                    onClick={() => act(app.id, "approve")}
                  >
                    Approve
                  </button>
                  <button
                    className="btn btn-danger-ghost btn-sm"
                    disabled={busyId === app.id}
                    onClick={() => act(app.id, "reject")}
                  >
                    Reject
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending_approval: "pill-pending",
    approved: "pill-approved",
    rejected: "pill-rejected",
    submitted: "pill-submitted",
  };
  const label = status.replace("_", " ");
  return <span className={`pill ${map[status] || "pill-default"}`}>{label}</span>;
}
