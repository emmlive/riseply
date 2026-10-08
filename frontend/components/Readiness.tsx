"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Fold from "@/components/Fold";
import { api, CareerCoachSessionType, ReadinessDimension, ReadinessLevel, ReadinessRole } from "@/lib/api";

// "Am I ready to get this job, and to do it?" answered from the coach's own
// scores for one target role. Two meters, a plain-words level for each, and
// the one session that would help most next.

export const LEVEL_TEXT: Record<ReadinessLevel, string> = {
  none: "Not started",
  starting: "Just starting",
  building: "Building",
  close: "Getting close",
  ready: "Ready",
};

const PART_NAMES: Record<string, string> = {
  interview: "Mock interviews",
  resume: "Resume coaching",
  walkthrough: "Task walkthroughs",
  drill: "Knowledge drills",
};

export const THRESHOLDS = "Just starting is under 50, Building 50 to 64, Getting close 65 to 79, Ready 80 and up, once at least 3 scored sessions are behind it.";

function Meter({ title, question, dim }: { title: string; question: string; dim: ReadinessDimension }) {
  const has = dim.score !== null;
  return (
    <div className="rd-meter">
      <div className="rd-head">
        <div>
          <div className="rd-title">{title}</div>
          <div className="rd-question">{question}</div>
        </div>
        <div className="rd-score" aria-label={has ? `${dim.score} out of 100` : "No score yet"}>{has ? dim.score : "—"}</div>
      </div>
      <div className="rd-track" role="img"
           aria-label={has ? `${title}: ${LEVEL_TEXT[dim.level]}, ${dim.score} out of 100` : `${title}: not started`}>
        <div className={`rd-fill rd-${dim.level}`} style={{ width: `${has ? Math.max(3, dim.score!) : 0}%` }} />
      </div>
      <div className="rd-level">
        <strong>{LEVEL_TEXT[dim.level]}</strong>
        {has && dim.early && <span> (early read, based on {dim.sessions} session{dim.sessions === 1 ? "" : "s"})</span>}
        {has && !dim.early && <span> (based on {dim.sessions} sessions)</span>}
      </div>
      <ul className="rd-parts">
        {dim.parts.map((p) => (
          <li key={p.session_type}>
            {PART_NAMES[p.session_type] || p.session_type}:{" "}
            {p.score !== null ? <strong>{p.score}</strong> : <span className="rd-none">not tried yet</span>}
            {p.sessions > 0 && <span className="rd-count"> ({p.sessions})</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RoleReadiness({ role, onPractice, compact }: {
  role: ReadinessRole;
  onPractice?: (role: string, type: CareerCoachSessionType) => void;
  compact?: boolean;
}) {
  return (
    <div className={`rd ${compact ? "rd-compact" : ""}`}>
      <div className="rd-meters">
        <Meter title="Ready to get the job" question="Interviews and resume" dim={role.get_job} />
        <Meter title="Ready to do the job" question="Real tasks and know-how" dim={role.do_job} />
      </div>
      <div className="rd-next">
        <span>{role.next_reason}</span>
        {onPractice && (
          <button className="btn btn-ghost btn-sm" onClick={() => onPractice(role.target_role, role.next_type)}>
            Practice this now
          </button>
        )}
      </div>
    </div>
  );
}

// The Career Coach side column: readiness for the role you are working on
// (or your most recent one when no session is open).
export function ReadinessCard({ activeRole, refreshKey, onPractice }: {
  activeRole?: string;
  refreshKey: string;
  onPractice: (role: string, type: CareerCoachSessionType) => void;
}) {
  const [roles, setRoles] = useState<ReadinessRole[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    api<ReadinessRole[]>("/progress/readiness").then((r) => { if (!cancelled) setRoles(r); }).catch(() => { if (!cancelled) setRoles([]); });
    return () => { cancelled = true; };
  }, [refreshKey]);

  if (roles === null) return null;
  const key = (activeRole || "").trim().toLowerCase();
  const mine = key ? roles.find((r) => r.target_role.trim().toLowerCase() === key) : roles[0];

  return (
    <Fold id="readiness" title="Your readiness" defaultOpen
          note={mine ? `${mine.get_job.score ?? "–"} / ${mine.do_job.score ?? "–"}` : undefined}>
      {mine ? (
        <>
          <p className="hint" style={{ margin: "0 0 10px" }}>For {mine.target_role}, from your scored sessions.</p>
          <RoleReadiness role={mine} onPractice={onPractice} compact />
          <p className="hint" style={{ margin: "10px 0 0" }}>
            <Link href="/dashboard/progress">See all your progress</Link>
          </p>
        </>
      ) : (
        <p className="hint" style={{ margin: "4px 0 0" }}>
          {activeRole
            ? `Finish a scored session for ${activeRole} (press End session) and your readiness for it appears here.`
            : "Finish a scored session and your readiness for that role appears here: whether you're ready to get the job, and ready to do it."}
        </p>
      )}
    </Fold>
  );
}
