"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Application, InterviewPrep, CompanyStats } from "@/lib/api";

const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "pending_approval", label: "Awaiting review" },
  { value: "approved", label: "Approved" },
  { value: "submitted", label: "Submitted" },
  { value: "interviewing", label: "Interviewing" },
  { value: "accepted", label: "Accepted" },
  { value: "rejected", label: "Rejected" },
];

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function ApplicationsPage() {
  const [apps, setApps] = useState<Application[]>([]);
  const [filter, setFilter] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [preps, setPreps] = useState<Record<number, InterviewPrep | "loading" | "none">>({});
  const [companyStats, setCompanyStats] = useState<Record<string, CompanyStats | "none">>({});

  async function load(status: string) {
    const qs = status ? `?status=${status}` : "";
    setApps(await api<Application[]>(`/applications${qs}`));
  }

  useEffect(() => { load(filter); }, [filter]);

  // Quietly fetch the live response-rate stat for each company shown,
  // so the Rise Index data surfaces right where it's most useful — next
  // to the actual application, not buried on a separate page.
  useEffect(() => {
    const companies = Array.from(new Set(apps.map((a) => a.job_company))).filter(
      (c) => c && !(c in companyStats)
    );
    companies.forEach((company) => {
      api<CompanyStats>(`/rise-index/company-stats?company=${encodeURIComponent(company)}`)
        .then((stats) => setCompanyStats((s) => ({ ...s, [company]: stats })))
        .catch(() => setCompanyStats((s) => ({ ...s, [company]: "none" })));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apps]);

  // Once interviewing applications are loaded, quietly check whether each
  // already has a prep brief, so it renders immediately instead of behind
  // an extra click.
  useEffect(() => {
    apps.filter((a) => a.status === "interviewing" && !(a.id in preps)).forEach((a) => {
      api<InterviewPrep>(`/applications/${a.id}/interview-prep`)
        .then((prep) => setPreps((p) => ({ ...p, [a.id]: prep })))
        .catch(() => setPreps((p) => ({ ...p, [a.id]: "none" })));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apps]);

  async function act(id: number, action: "approve" | "reject" | "mark-submitted" | "mark-interviewing" | "mark-accepted") {
    setBusyId(id);
    try {
      await api(`/applications/${id}/${action}`, { method: "POST" });
      await load(filter);
    } finally {
      setBusyId(null);
    }
  }

  async function generatePrep(id: number) {
    setPreps((p) => ({ ...p, [id]: "loading" }));
    try {
      const prep = await api<InterviewPrep>(`/applications/${id}/interview-prep`, { method: "POST" });
      setPreps((p) => ({ ...p, [id]: prep }));
    } catch (err: any) {
      setPreps((p) => ({ ...p, [id]: "none" }));
      alert(err.message || "Couldn't generate interview prep.");
    }
  }

  return (
    <div>
      <h1>Applications</h1>

      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
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

      {apps.map((app) => {
        const prep = preps[app.id];
        const stat = companyStats[app.job_company];
        return (
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
                {stat && stat !== "none" && (
                  <p className="hint" style={{ color: "var(--accent-hover)" }}>
                    {stat.response_rate}% of {stat.applied_count} Riseply applicants heard back from {stat.company}
                    {stat.avg_days_to_respond !== null && ` · ~${stat.avg_days_to_respond} days`}
                  </p>
                )}
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
                    <button className="btn btn-primary btn-sm" disabled={busyId === app.id}
                            onClick={() => act(app.id, "approve")}>Approve</button>
                    <button className="btn btn-danger-ghost btn-sm" disabled={busyId === app.id}
                            onClick={() => act(app.id, "reject")}>Reject</button>
                  </div>
                )}

                {app.status === "approved" && (
                  <button className="btn btn-primary btn-sm" disabled={busyId === app.id}
                          onClick={() => act(app.id, "mark-submitted")}>
                    Mark as applied
                  </button>
                )}

                {app.status === "submitted" && (
                  <button className="btn btn-ghost btn-sm" disabled={busyId === app.id}
                          onClick={() => act(app.id, "mark-interviewing")}>
                    Mark interviewing
                  </button>
                )}

                {app.status === "interviewing" && (
                  <button className="btn btn-primary btn-sm" disabled={busyId === app.id}
                          onClick={() => act(app.id, "mark-accepted")}>
                    Mark accepted
                  </button>
                )}

                {app.status === "accepted" && (
                  <Link href={`/dashboard/job-buddy?applicationId=${app.id}`} className="btn btn-primary btn-sm">
                    Open Job Buddy →
                  </Link>
                )}
              </div>
            </div>

            {app.status === "interviewing" && (
              <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
                {prep === "loading" && <p className="muted">Generating interview prep…</p>}
                {(!prep || prep === "none") && (
                  <button className="btn btn-ghost btn-sm" onClick={() => generatePrep(app.id)}>
                    Generate interview prep
                  </button>
                )}
                {prep && prep !== "loading" && prep !== "none" && (
                  <>
                    <h3 style={{ fontSize: "0.95rem" }}>Interview prep</h3>
                    <div className="brief">{prep.brief}</div>
                  </>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending_approval: "pill-pending",
    approved: "pill-approved",
    rejected: "pill-rejected",
    submitted: "pill-submitted",
    interviewing: "pill-interviewing",
    accepted: "pill-accepted",
  };
  const label = status.replace("_", " ");
  return <span className={`pill ${map[status] || "pill-default"}`}>{label}</span>;
}
