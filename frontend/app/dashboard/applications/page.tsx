"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Application, InterviewPrep, CompanyStats, downloadFile, formatSalary } from "@/lib/api";

const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "pending_approval", label: "Awaiting review" },
  { value: "approved", label: "Approved" },
  { value: "submitted", label: "Submitted" },
  { value: "interviewing", label: "Interviewing" },
  { value: "accepted", label: "Accepted" },
  { value: "rejected", label: "Rejected" },
];

export default function ApplicationsPage() {
  const [apps, setApps] = useState<Application[]>([]);
  const [filter, setFilter] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [preps, setPreps] = useState<Record<number, InterviewPrep | "loading" | "none">>({});
  const [companyStats, setCompanyStats] = useState<Record<string, CompanyStats | "none">>({});
  const [autoSubmitEligible, setAutoSubmitEligible] = useState<Record<number, boolean>>({});

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

  // Quietly check auto-submit eligibility for approved applications, so
  // the button only shows up when it could actually do something (server
  // has it enabled, and the job is on a supported ATS).
  useEffect(() => {
    const toCheck = apps.filter((a) => a.status === "approved" && !(a.id in autoSubmitEligible));
    toCheck.forEach((a) => {
      api<{ eligible: boolean }>(`/applications/${a.id}/auto-submit-eligible`)
        .then((r) => setAutoSubmitEligible((s) => ({ ...s, [a.id]: r.eligible })))
        .catch(() => setAutoSubmitEligible((s) => ({ ...s, [a.id]: false })));
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

  async function retailor(id: number) {
    setBusyId(id);
    try {
      await api(`/applications/${id}/retailor`, { method: "POST" });
      await load(filter);
    } catch (err: any) {
      alert(err.message || "Couldn't re-tailor this resume.");
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

  async function attemptAutoSubmit(id: number) {
    setBusyId(id);
    try {
      const result = await api<{ status: string; detail?: string }>(`/applications/${id}/auto-submit`, { method: "POST" });
      if (result.status === "submitted") {
        await load(filter);
      } else {
        alert(result.detail || "Needs a manual finish — the form may have been filled but not submitted.");
        await load(filter);
      }
    } catch (err: any) {
      alert(err.message || "Couldn't attempt auto-submit.");
    } finally {
      setBusyId(null);
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
        <div className="empty-state">
          {filter === "" && "No applications yet — head to Overview and click \"Find new matches\" to get started."}
          {filter === "pending_approval" && "Nothing waiting on your review right now."}
          {filter === "approved" && "Nothing approved yet — matches show up under \"Awaiting review\" first."}
          {filter === "submitted" && "Nothing submitted yet."}
          {filter === "interviewing" && "Nothing in an interview stage yet."}
          {filter === "accepted" && "No accepted offers yet — once you get one, mark it accepted to unlock Job Buddy for it."}
          {filter === "rejected" && "Nothing rejected — that's a good thing."}
        </div>
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
                {formatSalary(app) && (
                  <p className="hint" style={{ margin: "0 0 4px", fontWeight: 600 }}>{formatSalary(app)}</p>
                )}
                <p style={{ margin: "8px 0", fontSize: "0.9rem" }}>{app.match_reason}</p>
                {app.notes && <p className="hint">{app.notes}</p>}
                {stat && stat !== "none" && (
                  <p className="hint" style={{ color: "var(--accent-hover)" }}>
                    {stat.response_rate}% of {stat.applied_count} Riseply applicants heard back from {stat.company}
                    {stat.avg_days_to_respond !== null && ` · ~${stat.avg_days_to_respond} days`}
                  </p>
                )}
                <div style={{ display: "flex", gap: 10, marginTop: 10, fontSize: "0.85rem", alignItems: "center" }}>
                  <a href={app.job_url} target="_blank" rel="noreferrer">View posting →</a>
                  {app.has_tailored_resume_data && (
                    <a
                      href="#"
                      onClick={(e) => {
                        e.preventDefault();
                        downloadFile(`/applications/${app.id}/tailored-resume`, app.tailored_resume_path || "tailored_resume.docx")
                          .catch((err) => alert(err.message));
                      }}
                    >
                      Download tailored resume
                    </a>
                  )}
                  {!app.has_tailored_resume_data && app.tailored_resume_path && (
                    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span className="hint">Resume file unavailable (generated before a recent fix)</span>
                      <button className="btn btn-ghost btn-sm" disabled={busyId === app.id} onClick={() => retailor(app.id)}>
                        {busyId === app.id ? "Re-tailoring…" : "Re-tailor"}
                      </button>
                    </span>
                  )}
                </div>
                {app.tailoring_rationale && (
                  <div className="brief" style={{ marginTop: 10 }}>
                    <strong>What we changed:</strong> {app.tailoring_rationale}
                  </div>
                )}
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
                  <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
                    {autoSubmitEligible[app.id] && (
                      <button className="btn btn-ghost btn-sm" disabled={busyId === app.id}
                              onClick={() => attemptAutoSubmit(app.id)}
                              title="Fills and submits the form automatically — Greenhouse/Lever only">
                        Attempt auto-submit
                      </button>
                    )}
                    <button className="btn btn-primary btn-sm" disabled={busyId === app.id}
                            onClick={() => act(app.id, "mark-submitted")}>
                      Mark as applied
                    </button>
                  </div>
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
