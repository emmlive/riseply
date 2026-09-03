"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Application, Usage, RiseIndexMe, NearMiss, User, SearchProfile, Organization, showQuotaLimitModal, formatSalary, DirectReport, InternalJobApplication } from "@/lib/api";

export default function OverviewPage() {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [pending, setPending] = useState<Application[]>([]);
  const [rise, setRise] = useState<RiseIndexMe | null>(null);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [nearMisses, setNearMisses] = useState<NearMiss[]>([]);
  const [hasResume, setHasResume] = useState<boolean | null>(null);
  const [hasSearchedBefore, setHasSearchedBefore] = useState<boolean | null>(null);
  const [profileCount, setProfileCount] = useState<number | null>(null);
  const [userName, setUserName] = useState<string>("");
  const [checklistDismissed, setChecklistDismissed] = useState(
    typeof window !== "undefined" && localStorage.getItem("riseply_hide_getting_started") === "1"
  );
  // Same org-affiliation signal layout.tsx computes for nav visibility --
  // duplicated here rather than shared via context, matching how every
  // other page in this app (mentor-as-a-service, org-buddy,
  // internal-jobs) independently fetches its own /orgs/mine rather than
  // relying on a shared store that doesn't exist yet. orgCheckDone
  // guards against a flash of the full job-search dashboard before the
  // check resolves -- null (not yet known) intentionally renders
  // nothing rather than defaulting to either branch.
  const [hasOrgAdminAccess, setHasOrgAdminAccess] = useState<boolean | null>(null);
  const [isOrgEmployee, setIsOrgEmployee] = useState(false);
  const [directReports, setDirectReports] = useState<DirectReport[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<InternalJobApplication[]>([]);
  const [resolvedOrgId, setResolvedOrgId] = useState<number | null>(null);

  async function load() {
    // Promise.allSettled rather than Promise.all -- if literally ANY
    // one of these six calls fails (a transient error, or something
    // genuinely wrong with just one piece of this user's data), the
    // old all-or-nothing Promise.all meant the ENTIRE dashboard
    // silently rendered nothing: no usage, no pending applications, no
    // near-misses, nothing -- with the outer catch block only actually
    // handling 401s (see its comment) and swallowing every other
    // failure without so much as a console log. A single flaky
    // endpoint could make the whole dashboard look broken/empty for a
    // user with no indication why. Each piece now loads independently;
    // one failure degrades gracefully instead of taking everything else
    // down with it.
    const [uR, appsR, rR, meR, profilesR, nearMissesR] = await Promise.allSettled([
      api<Usage>("/usage"),
      api<Application[]>("/applications?status=pending_approval"),
      api<RiseIndexMe>("/rise-index/me"),
      api<User>("/me"),
      api<SearchProfile[]>("/profiles"),
      // Loads whatever near-misses were persisted from the LAST
      // "Find new matches" run -- without this, a page refresh would
      // show an empty "Closest this run" card even though a real
      // record of it exists now (see models.NearMissResult). Only
      // used to seed initial state; a fresh POST /pipeline/match
      // click still updates nearMisses directly via its own response
      // in runPipeline() below, same as before.
      api<NearMiss[]>("/pipeline/near-misses"),
    ]);

    if (uR.status === "fulfilled") setUsage(uR.value);
    if (appsR.status === "fulfilled") setPending(appsR.value);
    if (rR.status === "fulfilled") setRise(rR.value);
    if (meR.status === "fulfilled") {
      setHasResume(!!meR.value.resume_text.trim());
      // used_welcome_search (not usage.matches_used) is the right signal
      // here specifically because the welcome search deliberately does
      // NOT increment matches_used (see routers/pipeline.py's
      // skip_usage_metering) -- matches_used > 0 would incorrectly stay
      // false after someone's very first, deepest search of all.
      // used_welcome_search flips true exactly once, on that first
      // click, welcome or not, and stays true forever after.
      setHasSearchedBefore(meR.value.used_welcome_search);
      setUserName((meR.value.full_name || "").split(" ")[0]);
    }
    if (profilesR.status === "fulfilled") setProfileCount(profilesR.value.length);
    if (nearMissesR.status === "fulfilled") setNearMisses(nearMissesR.value);

    const results = [uR, appsR, rR, meR, profilesR, nearMissesR];
    const failures = results.filter((r) => r.status === "rejected");
    if (failures.length > 0) {
      console.error("Dashboard: some data failed to load", failures.map((f: any) => f.reason?.message || f.reason));
    }
    // Only surface a visible error if EVERYTHING failed (e.g. a real
    // network outage) -- a single endpoint failing degrades quietly
    // (that section just doesn't populate) rather than alarming the
    // person over one piece of a mostly-working page.
    if (failures.length === results.length) {
      setError("Couldn't load your dashboard right now — try refreshing the page.");
    }
  }

  function dismissChecklist() {
    setChecklistDismissed(true);
    localStorage.setItem("riseply_hide_getting_started", "1");
  }

  useEffect(() => {
    load();
    Promise.all([
      api<Organization[]>("/orgs/mine").catch(() => []),
      api<Application[]>("/applications").catch(() => []),
    ]).then(([orgs, apps]) => {
      setHasOrgAdminAccess(orgs.length > 0);
      const orgAffiliatedApp = apps.find((a) => a.organization_id !== null);
      setIsOrgEmployee(!!orgAffiliatedApp);

      // "My team" needs SOME org context to query against -- prefer an
      // org this person administers, otherwise fall back to whichever
      // org their own Application belongs to. A manager with neither
      // (no admin access AND no Application of their own in any org)
      // is a real but unusual edge case not covered here -- the
      // overwhelmingly common case is a manager who's also either an
      // admin or an employee at the same company they manage people
      // at, and /my-reports itself is safe to skip entirely rather
      // than guess at an org_id that might not exist.
      const orgId = orgs.length > 0 ? orgs[0].id : orgAffiliatedApp?.organization_id;
      if (orgId) {
        setResolvedOrgId(orgId);
        api<DirectReport[]>(`/orgs/${orgId}/my-reports`).then(setDirectReports).catch(() => {});
        api<InternalJobApplication[]>(`/orgs/${orgId}/my-pending-approvals`).then(setPendingApprovals).catch(() => {});
      }
    });
  }, []);

  async function decideApproval(applicationId: number, approve: boolean) {
    if (!resolvedOrgId) return;
    let reason = "";
    if (!approve) {
      const entered = prompt("Reason for declining (optional):");
      if (entered === null) return;  // cancelled
      reason = entered;
    }
    try {
      await api(`/orgs/${resolvedOrgId}/internal-job-applications/${applicationId}/decide`, {
        method: "POST",
        body: JSON.stringify({ approve, reason }),
      });
      setPendingApprovals((prev) => prev.filter((a) => a.id !== applicationId));
    } catch (err: any) {
      alert(err.message || "Couldn't record that decision.");
    }
  }

  async function runPipeline() {
    setRunning(true);
    setError("");
    setMessage("");
    setNearMisses([]);
    try {
      // Kick off a background discovery refresh but DON'T wait for it
      // to finish -- the job pool is shared across every user, not
      // scoped to this one click, so matching can proceed immediately
      // against whatever's already in the pool from prior discovery
      // runs (the nightly cron, other users' clicks) rather than
      // blocking this click on a fresh pass across 7+ external sources
      // completing first. That pass can genuinely take longer than
      // someone should have to wait on a button; it enriches the pool
      // for NEXT time; it was never strictly required before THIS
      // time's matching can run. Best-effort -- if even starting it
      // fails, matching against the existing pool still works fine, so
      // nothing here should block the click or surface an error for
      // what's just a background refresh.
      api("/pipeline/discover", { method: "POST" }).catch(() => {});

      const result = await api<{ queued_application_ids: number[]; usage_limit_reached: boolean; near_misses: NearMiss[]; hit_job_cap: boolean; is_welcome_search: boolean; jobs_searched: number }>(
        "/pipeline/match",
        { method: "POST" }
      );
      if (result.is_welcome_search) {
        // The one genuinely different message in this whole function --
        // deliberately leads with the depth number itself (100, not
        // "a lot" or "many"), since that concrete figure is the actual
        // "wow" -- and for a free-tier user, doubles as a real preview
        // of what Pro's every-click depth looks like, not just a one-
        // time bonus they'll never think about again.
        setMessage(
          `Your first search went deep — we scored ${result.jobs_searched} postings for you. ` +
          (result.queued_application_ids.length > 0
            ? `Found ${result.queued_application_ids.length} match${result.queued_application_ids.length === 1 ? "" : "es"} — check your email or the Applications tab.`
            : result.near_misses.length > 0
            ? "Nothing quite cleared your bar yet, but here's what came closest."
            : "Nothing close yet — try loosening your search criteria, or check back as new postings come in.")
        );
      } else {
        setMessage(
          result.queued_application_ids.length > 0
            ? `Found ${result.queued_application_ids.length} new match${result.queued_application_ids.length === 1 ? "" : "es"} — check your email or the Applications tab.`
            : result.near_misses.length > 0
            ? "Nothing quite cleared your bar this run — here's what came closest."
            : "No new matches this run. Try again later as new postings come in."
        );
      }
      if (result.usage_limit_reached) {
        setMessage((m) => m + " (Stopped early — monthly match limit reached.)");
        showQuotaLimitModal(
          "You've used up your monthly match limit for this billing cycle. " +
          "It resets at the start of your next cycle, or upgrade to Pro for a higher limit right away."
        );
      } else if (result.hit_job_cap) {
        setMessage((m) => m + " There are more unscored postings waiting — click \"Find new matches\" again to keep going, or check back after the nightly search runs.");
      }
      setNearMisses(result.near_misses);
      load();
    } catch (err: any) {
      setError(err.message || "Something went wrong running the search.");
    } finally {
      setRunning(false);
    }
  }

  // Org-affiliated users (admins and regular employees alike) get a
  // simple welcome instead of the full job-search dashboard below --
  // "Find new matches", pending applications, near-misses, and the
  // getting-started checklist all assume someone is personally
  // searching for a job, which isn't the case for someone here to
  // manage or participate in their employer's Buddy/Mentor/Internal
  // Jobs setup. hasOrgAdminAccess === null means the check hasn't
  // resolved yet -- render nothing rather than flashing the full
  // dashboard and then swapping it out a moment later.
  if (hasOrgAdminAccess === null) {
    return null;
  }
  if (hasOrgAdminAccess || isOrgEmployee) {
    return (
      <OrgAffiliatedOverview
        isAdmin={hasOrgAdminAccess} userName={userName} directReports={directReports}
        pendingApprovals={pendingApprovals} onDecideApproval={decideApproval}
      />
    );
  }

  return (
    <div>
      <div className="topbar">
        <h1>Overview</h1>
        <div style={{ textAlign: "right" }}>
          <button className="btn btn-primary" onClick={runPipeline} disabled={running}>
            {running ? "Searching…" : "Find new matches"}
          </button>
          {running && (
            <p className="hint" style={{ marginTop: 6, marginBottom: 0 }}>
              Scoring postings one at a time — this can take up to a minute or two.
            </p>
          )}
        </div>
      </div>

      {!checklistDismissed && hasResume !== null && profileCount !== null && (hasResume === false || profileCount === 0 || !hasSearchedBefore) && (
        <div className="card" style={{ borderColor: "var(--accent)" }}>
          <div className="card-row" style={{ alignItems: "flex-start" }}>
            <h3 style={{ margin: 0 }}>
              {hasResume === false && profileCount === 0
                ? `Welcome${userName ? `, ${userName}` : ""}! Here's what to do next`
                : "Getting started"}
            </h3>
            <button className="btn btn-ghost btn-sm" onClick={dismissChecklist}>Dismiss</button>
          </div>
          <div style={{ marginTop: 10 }}>
            <ChecklistStep done={hasResume} label="Add your resume" href="/dashboard/resume" />
            <ChecklistStep done={profileCount > 0} label="Create a search profile" href="/dashboard/profiles" />
            <ChecklistStep done={!!hasSearchedBefore} label='Click "Find new matches" above' />
            <ChecklistStep done={pending.length === 0 && !!hasSearchedBefore} label="Review your matches as they come in" href="/dashboard/applications" />
          </div>
          <p className="hint" style={{ marginTop: 10, marginBottom: 0 }}>
            Every match lands here for you to approve or reject — nothing gets submitted
            anywhere without you saying so first.
          </p>
        </div>
      )}

      {message && (
        <div className="card" style={{ borderColor: "var(--accent)" }}>
          {message}
        </div>
      )}
      {error && <p className="error-text">{error}</p>}

      {nearMisses.length > 0 && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Closest this run</h3>
          <p className="hint" style={{ marginTop: -4, marginBottom: 12 }}>
            None of these cleared your profile's match threshold, but they were the nearest —
            worth a look, or a sign to loosen your search criteria a bit.
          </p>
          {nearMisses.map((nm, i) => (
            <div key={i} className="points-event-row">
              <div>
                <div style={{ fontWeight: 600 }}>{nm.title} — {nm.company}</div>
                {nm.location_mismatch && (
                  <div className="hint" style={{ color: "var(--warning, #C97A2B)", fontWeight: 600 }}>
                    Outside your preferred location
                  </div>
                )}
                <div className="hint">{nm.reason}</div>
                {formatSalary(nm) && <div className="hint">{formatSalary(nm)}</div>}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className="ticket">match <span className="score">{nm.score}%</span></span>
                <a href={nm.url} target="_blank" rel="noopener noreferrer" className="hint">View →</a>
              </div>
            </div>
          ))}
        </div>
      )}

      {rise && (
        <div className="rise-hero">
          <div className="rise-stat">
            <div className="value">
              <span className="streak-flame">🔥</span> {rise.current_streak}
            </div>
            <div className="label">Day streak</div>
          </div>
          <div className="rise-stat">
            <div className="value">{rise.rise_points}</div>
            <div className="label">Rise points</div>
          </div>
          <Link href="/dashboard/rise-index" className="rise-stat" style={{ textDecoration: "none", color: "inherit", display: "flex", flexDirection: "column", justifyContent: "center" }}>
            <div className="label" style={{ color: "var(--accent-hover)", fontWeight: 600 }}>See trending companies →</div>
          </Link>
        </div>
      )}

      {usage && (
        <div className="card">
          <h3>This month's usage</h3>
          <div style={{ display: "flex", gap: 32, marginTop: 10, flexWrap: "wrap" }}>
            <UsageBar label="Job matches scored" used={usage.matches_used} limit={usage.matches_limit} />
            <UsageBar label="Resumes tailored" used={usage.tailored_resumes_used} limit={usage.tailored_resumes_limit} />
            <UsageBar label="Interview preps" used={usage.interview_preps_used} limit={usage.interview_preps_limit} />
            <UsageBar label="Job Buddy messages" used={usage.job_buddy_messages_used} limit={usage.job_buddy_messages_limit} />
          </div>
        </div>
      )}

      <h2 style={{ marginTop: 28 }}>Awaiting your review</h2>
      {pending.length === 0 ? (
        <div className="empty-state">
          No applications waiting on you right now. Run a search, or check back later.
        </div>
      ) : (
        pending.slice(0, 5).map((app) => (
          <div key={app.id} className="card">
            <div className="card-row">
              <div>
                <h3>{app.job_title} — {app.job_company}</h3>
                <p className="muted" style={{ margin: 0 }}>{app.job_location}</p>
              </div>
              <span className={`ticket ${app.match_score >= 80 ? "high" : ""}`}>
                match <span className="score">{app.match_score}%</span>
              </span>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

function OrgAffiliatedOverview({ isAdmin, userName, directReports, pendingApprovals, onDecideApproval }: { isAdmin: boolean; userName: string; directReports: DirectReport[]; pendingApprovals: InternalJobApplication[]; onDecideApproval: (id: number, approve: boolean) => void }) {
  return (
    <div>
      <h1>Welcome{userName ? `, ${userName}` : ""}!</h1>
      {isAdmin ? (
        <>
          <p className="muted">
            Here's where to manage your organization's onboarding, mentoring, and internal
            mobility programs.
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16, marginTop: 8 }}>
            <Link href="/dashboard/org-buddy" className="card" style={{ textDecoration: "none", color: "inherit", display: "block" }}>
              <h3 style={{ marginTop: 0 }}>Org Buddy</h3>
              <p className="hint" style={{ margin: 0 }}>
                Onboarding checklists, company content, roster, and SSO for new employees.
              </p>
            </Link>
            <Link href="/dashboard/mentor-as-a-service" className="card" style={{ textDecoration: "none", color: "inherit", display: "block" }}>
              <h3 style={{ marginTop: 0 }}>Mentor as a Service</h3>
              <p className="hint" style={{ margin: 0 }}>
                1:1 mentor pairing, group cohorts, reciprocal pairs, and scheduled meetings.
              </p>
            </Link>
            <Link href="/dashboard/internal-jobs" className="card" style={{ textDecoration: "none", color: "inherit", display: "block" }}>
              <h3 style={{ marginTop: 0 }}>Internal Jobs</h3>
              <p className="hint" style={{ margin: 0 }}>
                Post openings at your own company and let employees apply from Job Buddy.
              </p>
            </Link>
          </div>
        </>
      ) : (
        <>
          <p className="muted">
            Job Buddy is your home base — onboarding, your mentor, internal openings, and
            everything else in one place.
          </p>
          <Link href="/dashboard/job-buddy" className="btn btn-primary" style={{ display: "inline-block", textDecoration: "none" }}>
            Go to Job Buddy
          </Link>
        </>
      )}

      {directReports.length > 0 && (
        <div className="card" style={{ marginTop: 24 }}>
          <h3 style={{ marginTop: 0 }}>My team</h3>
          <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
            Progress for the people who report to you — aggregate numbers only, never
            conversation content, career goals, or meeting notes.
          </p>
          {directReports.map((r) => (
            <div key={r.application_id} style={{ padding: "8px 0", borderBottom: "1px solid var(--border, #eee)" }}>
              <div style={{ fontWeight: 600 }}>
                {r.user_full_name}
                {r.department_name && <span className="hint"> · {r.department_name}</span>}
              </div>
              <div className="hint">
                {r.checklist_completion_pct}% onboarding complete
                {r.mentor_name ? ` · mentor: ${r.mentor_name}` : " · no mentor assigned"}
                {r.certifications_total > 0 && (
                  ` · ${r.certifications_completed}/${r.certifications_total} certifications current`
                  + (r.certifications_expired > 0 ? ` (${r.certifications_expired} expired)` : "")
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {pendingApprovals.length > 0 && (
        <div className="card" style={{ marginTop: 24 }}>
          <h3 style={{ marginTop: 0 }}>Waiting on your approval</h3>
          <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
            Internal job applications from people who list you as their manager.
          </p>
          {pendingApprovals.map((a) => (
            <div key={a.id} style={{ padding: "8px 0", borderBottom: "1px solid var(--border, #eee)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
                <div>
                  <div style={{ fontWeight: 600 }}>
                    {a.applicant_name} <span className="hint">→ {a.posting_title}</span>
                  </div>
                  {a.note && <div className="hint">{a.note}</div>}
                </div>
                <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                  <button className="btn btn-primary btn-sm" onClick={() => onDecideApproval(a.id, true)}>Approve</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => onDecideApproval(a.id, false)}>Decline</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function UsageBar({ label, used, limit }: { label: string; used: number; limit: number }) {
  const pct = Math.min(100, Math.round((used / Math.max(limit, 1)) * 100));
  return (
    <div style={{ flex: "1 1 180px", minWidth: 180 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.82rem" }}>
        <span className="muted">{label}</span>
        <span className="mono">{used} / {limit}</span>
      </div>
      <div style={{ height: 6, background: "var(--paper)", borderRadius: 4, marginTop: 6, overflow: "hidden" }}>
        <div style={{
          width: `${pct}%`, height: "100%",
          background: pct >= 90 ? "var(--danger)" : "var(--accent)",
        }} />
      </div>
    </div>
  );
}

function ChecklistStep({ done, label, href }: { done: boolean; label: string; href?: string }) {
  const content = (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0" }}>
      <span style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        width: 18, height: 18, borderRadius: "50%", fontSize: "0.7rem", flexShrink: 0,
        background: done ? "var(--accent)" : "transparent",
        border: done ? "none" : "1px solid var(--border)",
        color: done ? "#fff" : "transparent",
      }}>
        ✓
      </span>
      <span style={{ textDecoration: done ? "line-through" : "none", color: done ? "var(--ink-muted)" : "var(--ink)" }}>
        {label}
      </span>
    </div>
  );
  if (href && !done) {
    return <Link href={href} style={{ display: "block" }}>{content}</Link>;
  }
  return content;
}
