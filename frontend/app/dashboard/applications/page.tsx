"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import ResumePreview from "@/components/ResumePreview";
import { api, Application, InterviewPrep, KeywordGaps, Followup, CompanyStats, downloadFile, formatSalary, formatWhen } from "@/lib/api";

const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "pending_approval", label: "Awaiting review" },
  { value: "approved", label: "Approved" },
  { value: "submitted", label: "Submitted" },
  { value: "interviewing", label: "Interviewing" },
  { value: "accepted", label: "Accepted" },
  { value: "rejected", label: "Rejected" },
  { value: "closed", label: "Closed postings" },
];

// A distinct pseudo-filter, not a real status -- archived is its own
// dimension (any status can be archived), so this is handled specially
// in load() below rather than being just another value in the status
// query param.
const ARCHIVED_FILTER = "__archived__";

// Pasted text that is probably not a job description: too short to describe
// a role, or a sign-in / cookie wall copied by mistake. Only warns; the
// person can still add it.
function looksLikeWrongText(text: string): boolean {
  const t = text.trim().toLowerCase();
  if (t.length < 80) return false; // the Add button is already disabled
  if (t.length < 300) return true;
  return /(sign in to|log in to|join linkedin|enable cookies|verify you are human|are you a robot|accept all cookies)/.test(t) && t.length < 1200;
}

const DAY_MS = 24 * 60 * 60 * 1000;

function daysSince(iso: string | null | undefined): number {
  if (!iso) return 0;
  const hasZone = /([zZ]|[+-]\d\d:?\d\d)$/.test(iso);
  const t = new Date(hasZone ? iso : iso + "Z").getTime();
  return isNaN(t) ? 0 : Math.floor((Date.now() - t) / DAY_MS);
}

// One plain line on each card saying what the person does next. Riseply
// can't see what happens on an employer's site, so each stage moves on
// only when the person presses its button.
function nextStepLine(app: Application): string {
  switch (app.status) {
    case "pending_approval":
      return app.job_open === false ? "" : "Next: open the posting and read the tailored resume. Approve it if you want to apply, or press I already applied if you have.";
    case "approved": {
      const days = daysSince(app.status_updated_at);
      return days >= 3
        ? `You approved this ${days} days ago. Did you apply? Press Mark as applied. If you're skipping it, Reject or Archive it.`
        : "Next: apply on the employer's site, then press Mark as applied. Riseply can't see your application, so it only knows when you tell it.";
    }
    case "submitted":
      return "Applied. When the company invites you to interview, press Mark interviewing.";
    case "interviewing":
      return "If you get an offer, press Mark accepted.";
    default:
      return "";
  }
}

export default function ApplicationsPage() {
  const [apps, setApps] = useState<Application[]>([]);
  const [filter, setFilter] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState("");
  const [preps, setPreps] = useState<Record<number, InterviewPrep | "loading" | "none">>({});
  const [keywordGaps, setKeywordGaps] = useState<Record<number, KeywordGaps | "loading" | "none">>({});
  const [followups, setFollowups] = useState<Record<number, Followup | "loading" | "none">>({});
  const [companyStats, setCompanyStats] = useState<Record<string, CompanyStats | "none">>({});
  const [autoSubmitEligible, setAutoSubmitEligible] = useState<Record<number, boolean>>({});
  const [previewApp, setPreviewApp] = useState<Application | null>(null);

  const [loadError, setLoadError] = useState("");
  const [loaded, setLoaded] = useState(false);

  const [guideHidden, setGuideHidden] = useState(true);
  useEffect(() => {
    try { setGuideHidden(localStorage.getItem("riseply_hide_review_guide") === "1"); } catch { setGuideHidden(false); }
  }, []);
  function hideGuide() {
    setGuideHidden(true);
    try { localStorage.setItem("riseply_hide_review_guide", "1"); } catch {}
  }

  const [adding, setAdding] = useState(false);
  const [addBusy, setAddBusy] = useState(false);
  const [addedNote, setAddedNote] = useState("");
  const [alreadyApplied, setAlreadyApplied] = useState(false);
  const [addError, setAddError] = useState("");
  const [addForm, setAddForm] = useState({ description: "", url: "", title: "", company: "" });

  async function load(status: string) {
    // A failed load must not look like "you have no applications".
    try {
      if (status === ARCHIVED_FILTER) {
        setApps(await api<Application[]>("/applications?archived=true"));
      } else {
        const qs = status ? `?status=${status}` : "";
        setApps(await api<Application[]>(`/applications${qs}`));
      }
      setLoadError("");
    } catch (e: any) {
      setLoadError(e?.message || "We couldn't load your applications.");
    } finally {
      setLoaded(true);
    }
  }

  useEffect(() => { load(filter); }, [filter]);

  async function addJob(e: React.FormEvent) {
    e.preventDefault();
    setAddBusy(true);
    setAddError("");
    try {
      await api<Application>("/applications/import", { method: "POST", body: JSON.stringify({ ...addForm, already_applied: alreadyApplied }) });
      setAddForm({ description: "", url: "", title: "", company: "" });
      setAdding(false);
      setFilter("");
      await load("");
      setActionError("");
      setAddedNote(alreadyApplied
        ? "Job saved as Submitted. When the company invites you to interview, press Mark interviewing."
        : "Job added. Read the tailored resume with Preview resume, check the posting is still open, then apply on the employer's site.");
      setAlreadyApplied(false);
    } catch (err: any) {
      setAddError(err?.message || "Couldn't add that job. Try again.");
    } finally {
      setAddBusy(false);
    }
  }

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
    setActionError("");
    try {
      await api(`/applications/${id}/${action}`, { method: "POST" });
    } catch (e: any) {
      // e.g. the posting closed since it was matched: say so, and the
      // refresh below moves it out of the way.
      setActionError(e?.message || "That didn't work. Try again.");
    }
    try {
      await load(filter);
    } finally {
      setBusyId(null);
    }
  }

  async function toggleArchive(id: number, archive: boolean) {
    setBusyId(id);
    try {
      await api(`/applications/${id}/${archive ? "archive" : "unarchive"}`, { method: "POST" });
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

  async function checkKeywordGaps(id: number) {
    setKeywordGaps((g) => ({ ...g, [id]: "loading" }));
    try {
      const result = await api<KeywordGaps>(`/applications/${id}/keyword-gaps`, { method: "POST" });
      setKeywordGaps((g) => ({ ...g, [id]: result }));
    } catch (err: any) {
      setKeywordGaps((g) => ({ ...g, [id]: "none" }));
      alert(err.message || "Couldn't check keyword gaps.");
    }
  }

  async function draftFollowup(id: number) {
    setFollowups((f) => ({ ...f, [id]: "loading" }));
    try {
      const result = await api<Followup>(`/applications/${id}/draft-followup`, { method: "POST" });
      setFollowups((f) => ({ ...f, [id]: result }));
    } catch (err: any) {
      setFollowups((f) => ({ ...f, [id]: "none" }));
      alert(err.message || "Couldn't draft a follow-up.");
    }
  }

  async function attemptAutoSubmit(id: number) {
    // Guard: this is the one button that really sends an application to an
    // employer, so make the person confirm it.
    if (!window.confirm("This fills in and submits the application to the employer using your tailored resume. Have you read the resume and confirmed the job is still open?")) return;
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
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ margin: 0 }}>Applications</h1>
        <button className="btn btn-primary btn-sm" onClick={() => setAdding((v) => !v)} aria-expanded={adding}>
          {adding ? "Close" : "Add a job"}
        </button>
      </div>

      {!guideHidden && apps.some((a) => a.status === "pending_approval") && (
        <div className="card" style={{ marginTop: 16, borderColor: "var(--accent)" }}>
          <div className="card-row" style={{ alignItems: "flex-start" }}>
            <h3 style={{ margin: 0 }}>Before you approve a match</h3>
            <button className="btn btn-ghost btn-sm" onClick={hideGuide}>Got it</button>
          </div>
          <p className="hint" style={{ marginTop: 8 }}>
            1. Open <strong>View posting</strong> and check the job is still taking applications. Postings close without warning.
          </p>
          <p className="hint">
            2. Open <strong>Preview resume</strong> and read the tailored resume. It only rearranges and rewords what is already on your resume, but you are the one who signs it.
          </p>
          <p className="hint">
            3. <strong>Approve</strong> only moves the job to Approved. Nothing is sent to the employer. Apply on their site, then press <strong>Mark as applied</strong>.
          </p>
          <p className="hint" style={{ marginBottom: 0 }}>
            Found a job somewhere else? Use <strong>Add a job</strong> above to get a tailored resume for it.
          </p>
        </div>
      )}

      {adding && (
        <form className="card" onSubmit={addJob} style={{ marginTop: 16 }}>
          <h3>Add a job you found somewhere else</h3>
          <p className="hint">
            Open the posting on Indeed, LinkedIn or the company's site, copy the whole job description, and paste it here.
            Riseply scores it against your resume and tailors your resume for it.
          </p>
          <p className="hint">
            Copy from the posting page itself, from the title down to the requirements. A login page or a
            search results list won't work, because the text has to be the job. Add the link too, so you can
            come back and apply.
          </p>
          <label htmlFor="add-description" style={{ fontWeight: 600 }}>Job description</label>
          <textarea
            id="add-description" required minLength={80} rows={9}
            value={addForm.description}
            onChange={(e) => setAddForm({ ...addForm, description: e.target.value })}
            placeholder="Paste the full posting here"
            style={{ width: "100%", marginBottom: 12 }}
          />
          <label htmlFor="add-url" style={{ fontWeight: 600 }}>Link to the posting (optional)</label>
          <input
            id="add-url" type="url" value={addForm.url}
            onChange={(e) => setAddForm({ ...addForm, url: e.target.value })}
            placeholder="https://"
            style={{ width: "100%", marginBottom: 12 }}
          />
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <div style={{ flex: "1 1 220px" }}>
              <label htmlFor="add-title" style={{ fontWeight: 600 }}>Job title (optional)</label>
              <input id="add-title" value={addForm.title} onChange={(e) => setAddForm({ ...addForm, title: e.target.value })} style={{ width: "100%" }} />
            </div>
            <div style={{ flex: "1 1 220px" }}>
              <label htmlFor="add-company" style={{ fontWeight: 600 }}>Company (optional)</label>
              <input id="add-company" value={addForm.company} onChange={(e) => setAddForm({ ...addForm, company: e.target.value })} style={{ width: "100%" }} />
            </div>
          </div>
          <p className="hint">Leave the title and company blank and Riseply reads them from the text.</p>
          <label style={{ display: "flex", gap: 8, alignItems: "center", margin: "8px 0 12px" }}>
            <input type="checkbox" checked={alreadyApplied} onChange={(e) => setAlreadyApplied(e.target.checked)} />
            I already applied to this job (save it as Submitted, no resume tailoring)
          </label>
          {looksLikeWrongText(addForm.description) && (
            <p className="cc-error" role="status">
              This doesn't look like a full job posting. If you pasted a sign-in page, a cookie notice or a list of
              jobs, go back and copy the description itself. You can still add it if it's right.
            </p>
          )}
          {addError && <p className="cc-error" role="alert">{addError}</p>}
          <button className="btn btn-primary" type="submit" disabled={addBusy || addForm.description.trim().length < 80}>
            {addBusy ? "Reading the job…" : alreadyApplied ? "Add job as Submitted" : "Add job and tailor my resume"}
          </button>
        </form>
      )}

      <div style={{ display: "flex", gap: 8, margin: "20px 0", flexWrap: "wrap" }}>
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
        <button
          className="btn btn-ghost btn-sm"
          style={filter === ARCHIVED_FILTER ? { background: "var(--accent-soft)", color: "var(--accent-hover)", borderColor: "var(--accent)" } : {}}
          onClick={() => setFilter(ARCHIVED_FILTER)}
        >
          Archived
        </button>
      </div>

      {(() => {
        const waiting = apps.filter((a) => a.status === "approved" && daysSince(a.status_updated_at) >= 3).length;
        return waiting > 0 ? (
          <div className="card" role="status" style={{ borderColor: "var(--amber)", marginTop: 16 }}>
            {waiting} approved job{waiting === 1 ? " is" : "s are"} still waiting. If you applied, press <strong>Mark as applied</strong> on {waiting === 1 ? "it" : "each one"} so your progress stays accurate. If not, apply soon, because postings close.
          </div>
        ) : null;
      })()}

      {addedNote && (
        <div className="card" role="status" style={{ borderColor: "var(--accent)" }}>
          <div className="card-row" style={{ alignItems: "flex-start" }}>
            <span>{addedNote}</span>
            <button className="btn btn-ghost btn-sm" onClick={() => setAddedNote("")}>Dismiss</button>
          </div>
        </div>
      )}

      {actionError && <p className="cc-error" role="alert">{actionError}</p>}

      {loadError && (
        <div className="cc-error" role="alert">
          We couldn&apos;t load your applications: {loadError}{" "}
          <button className="btn btn-ghost btn-sm" onClick={() => load(filter)}>Try again</button>
        </div>
      )}

      {loaded && !loadError && apps.length === 0 && (
        <div className="empty-state">
          {filter === "" && "No applications yet — head to Overview and click \"Find new matches\" to get started."}
          {filter === "pending_approval" && "Nothing waiting on your review right now."}
          {filter === "approved" && "Nothing approved yet — matches show up under \"Awaiting review\" first."}
          {filter === "submitted" && "Nothing submitted yet."}
          {filter === "interviewing" && "Nothing in an interview stage yet."}
          {filter === "accepted" && "No accepted offers yet — once you get one, mark it accepted to unlock Job Buddy for it."}
          {filter === "rejected" && "Nothing rejected — that's a good thing."}
          {filter === "closed" && "No closed postings. When a job you were matched to closes, it moves here."}
          {filter === ARCHIVED_FILTER && "Nothing archived — archive an application to tuck it out of your default view without losing it."}
        </div>
      )}

      {apps.map((app) => {
        const prep = preps[app.id];
        const gaps = keywordGaps[app.id];
        const followup = followups[app.id];
        const daysSinceSubmitted = app.submitted_at
          ? Math.floor((Date.now() - new Date(app.submitted_at).getTime()) / (1000 * 60 * 60 * 24))
          : null;
        const showFollowupNudge = app.status === "submitted" && daysSinceSubmitted !== null && daysSinceSubmitted >= 7;
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
                {nextStepLine(app) && (
                  <p className="hint" style={{ color: "var(--accent-hover)" }}>{nextStepLine(app)}</p>
                )}
                {stat && stat !== "none" && (
                  <p className="hint" style={{ color: "var(--accent-hover)" }}>
                    {stat.response_rate}% of {stat.applied_count} Riseply applicants heard back from {stat.company}
                    {stat.avg_days_to_respond !== null && ` · ~${stat.avg_days_to_respond} days`}
                  </p>
                )}
                <div style={{ display: "flex", gap: 10, marginTop: 10, fontSize: "0.85rem", alignItems: "center" }}>
                  <a href={app.job_url} target="_blank" rel="noreferrer">View posting →</a>
                  <button
                    className="btn btn-ghost btn-sm"
                    style={{ padding: "2px 8px" }}
                    disabled={busyId === app.id}
                    onClick={() => toggleArchive(app.id, !app.is_archived)}
                  >
                    {app.is_archived ? "Unarchive" : "Archive"}
                  </button>
                  {app.has_tailored_resume_data && (
                    <button
                      className="btn btn-ghost btn-sm"
                      style={{ padding: "2px 8px" }}
                      onClick={() => setPreviewApp(app)}
                    >
                      Preview resume
                    </button>
                  )}
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
                  {!app.has_tailored_resume_data && !app.tailored_resume_path && (
                    // Original tailoring never happened at all for this
                    // application -- e.g. it hit the monthly tailoring
                    // limit, or a transient API error, at match time (see
                    // pipeline_runner.py, which sets app.notes to a
                    // message literally saying "you can retry from the
                    // dashboard later" in this exact case). Without this
                    // branch there was NO button at all here -- the retry
                    // the notes text promised didn't actually exist
                    // anywhere in the UI, which is what "the tailored
                    // resume feature isn't visible or accessible" was
                    // actually describing.
                    <button className="btn btn-ghost btn-sm" disabled={busyId === app.id} onClick={() => retailor(app.id)}>
                      {busyId === app.id ? "Tailoring…" : "Tailor resume"}
                    </button>
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
                <span className="hint" style={{ fontSize: "0.8rem" }}>Found {formatWhen(app.created_at)}</span>

                {app.status === "pending_approval" && app.job_open === false && (
                  <span className="hint">This posting has closed.</span>
                )}
                {app.status === "pending_approval" && app.job_open !== false && (
                  <div style={{ display: "flex", gap: 6 }}>
                    <button className="btn btn-primary btn-sm" disabled={busyId === app.id}
                            onClick={() => act(app.id, "approve")}>Approve</button>
                    <button className="btn btn-danger-ghost btn-sm" disabled={busyId === app.id}
                            onClick={() => act(app.id, "reject")}>Reject</button>
                  </div>
                )}
                {app.status === "pending_approval" && (
                  <button className="btn btn-ghost btn-sm" disabled={busyId === app.id}
                          title="Use this if you already applied on the employer's site"
                          onClick={() => act(app.id, "mark-submitted")}>I already applied</button>
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

            <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
              {gaps === "loading" && <p className="muted">Checking keyword gaps…</p>}
              {(!gaps || gaps === "none") && (
                <button className="btn btn-ghost btn-sm" onClick={() => checkKeywordGaps(app.id)}>
                  Check keyword gaps
                </button>
              )}
              {gaps && gaps !== "loading" && gaps !== "none" && (
                <>
                  <h3 style={{ fontSize: "0.95rem", marginBottom: 4 }}>
                    Keyword gaps — {gaps.present.length}/{gaps.present.length + gaps.missing.length} matched
                  </h3>
                  <p className="hint" style={{ marginTop: 0, marginBottom: 8 }}>
                    Specific things this posting emphasizes, and whether your resume actually reflects each one —
                    the concrete version of the match score above.
                  </p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {gaps.present.map((k) => (
                      <span key={k} className="pill pill-approved">✓ {k}</span>
                    ))}
                    {gaps.missing.map((k) => (
                      <span key={k} className="pill pill-rejected">✗ {k}</span>
                    ))}
                  </div>
                </>
              )}
            </div>

            {showFollowupNudge && (
              <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
                {followup === "loading" && <p className="muted">Drafting a follow-up…</p>}
                {(!followup || followup === "none") && (
                  <>
                    <p className="hint" style={{ margin: "0 0 8px" }}>
                      It's been {daysSinceSubmitted} days since you applied with no update — worth a follow-up.
                    </p>
                    <button className="btn btn-ghost btn-sm" onClick={() => draftFollowup(app.id)}>
                      Draft a follow-up
                    </button>
                  </>
                )}
                {followup && followup !== "loading" && followup !== "none" && (
                  <>
                    <h3 style={{ fontSize: "0.95rem" }}>Suggested follow-up</h3>
                    <div className="brief">{followup.message}</div>
                  </>
                )}
              </div>
            )}

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
      {previewApp && (
        <ResumePreview
          applicationId={previewApp.id}
          company={previewApp.job_company}
          onClose={() => setPreviewApp(null)}
          onSaved={() => load(filter)}
        />
      )}
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
    closed: "pill-rejected",
  };
  const label = status === "closed" ? "posting closed" : status.replace("_", " ");
  return <span className={`pill ${map[status] || "pill-default"}`}>{label}</span>;
}
