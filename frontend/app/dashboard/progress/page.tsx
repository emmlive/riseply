"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchProgress, ProgressData } from "@/lib/api";
import { Funnel, ScoreChart, WeekChart } from "@/components/ProgressCharts";
import { RoleReadiness, THRESHOLDS } from "@/components/Readiness";

function changeText(change: number | null, scored: number): string {
  if (change === null) return scored < 2 ? "Finish two scored sessions to see a trend" : "";
  if (change > 0) return `Up ${change} point${change === 1 ? "" : "s"} lately`;
  if (change < 0) return `Down ${-change} point${change === -1 ? "" : "s"} lately`;
  return "Holding steady";
}

function Tile({ label, value, sub, tone }: { label: string; value: string | number; sub?: string; tone?: "up" | "down" }) {
  return (
    <div className="pg-tile">
      <div className="pg-tile-label">{label}</div>
      <div className="pg-tile-value">{value}</div>
      {sub && <div className={`pg-tile-sub ${tone || ""}`}>{sub}</div>}
    </div>
  );
}

export default function ProgressPage() {
  const [data, setData] = useState<ProgressData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchProgress().then(setData).catch((e) => setError(e?.message || "We couldn't load your progress. Try again in a moment."));
  }, []);

  if (error) return <div><h1>Progress</h1><p className="cc-error" role="alert">{error}</p></div>;
  if (!data) return <div><h1>Progress</h1><p className="hint">Loading your progress…</p></div>;

  const { practice: p, job_search: js } = data;
  const f = js.funnel;
  const hasPractice = p.sessions_completed > 0;
  const hasJobs = f.matched > 0;
  const tone = p.change === null ? undefined : p.change > 0 ? "up" : p.change < 0 ? "down" : undefined;

  return (
    <div className="pg">
      <h1>Progress</h1>
      <p className="muted">
        How your practice and your job search are going. Everything here comes from what you have already
        done in Riseply, so it fills in as you use it.
      </p>

      <div className="pg-tiles">
        <Tile label="Practice sessions finished" value={p.sessions_completed}
              sub={p.sessions_in_progress > 0 ? `${p.sessions_in_progress} still open` : undefined} />
        <Tile label="Average practice score" value={p.avg_score !== null ? Math.round(p.avg_score) : "—"}
              sub={changeText(p.change, p.scored_sessions)} tone={tone} />
        <Tile label="Applications sent" value={f.applied}
              sub={f.matched ? `of ${f.matched} matched` : undefined} />
        <Tile label="Reached an interview" value={f.interviewing}
              sub={js.interview_rate !== null ? `${js.interview_rate}% of applications` : f.applied ? "Rate shows after 5 applications" : undefined} />
        <Link href="/dashboard/rise-index" className="pg-tile pg-tile-link">
          <div className="pg-tile-label">Day streak</div>
          <div className="pg-tile-value"><span className="streak-flame">🔥</span> {data.current_streak}</div>
          <div className="pg-tile-sub">Longest {data.longest_streak}. See Rise Index</div>
        </Link>
      </div>

      {data.readiness.length > 0 && (
        <>
          <h2 className="pg-h2">Readiness</h2>
          <p className="hint" style={{ margin: "-4px 0 10px" }}>
            How ready you are for each role you have practiced, from the Career Coach&apos;s scores.
            It is the coach&apos;s read on your practice, not a prediction of whether you will be hired.
            {" "}{THRESHOLDS}
          </p>
          {data.readiness.map((r) => (
            <div className="card" key={r.target_role}>
              <h3 className="pg-card-title" style={{ marginBottom: 12 }}>
                {r.target_role}
                <span className="hint" style={{ fontWeight: 400 }}> ({r.scored_sessions} scored session{r.scored_sessions === 1 ? "" : "s"})</span>
              </h3>
              <RoleReadiness role={r} />
              <p className="hint" style={{ margin: "10px 0 0" }}>
                <Link href="/dashboard/career-coach">Open the Career Coach</Link> to practice.
              </p>
            </div>
          ))}
        </>
      )}

      <h2 className="pg-h2">Practice</h2>
      {!hasPractice ? (
        <div className="card">
          <p style={{ margin: 0 }}>
            No finished practice sessions yet. Finish a session in the <Link href="/dashboard/career-coach">Career Coach</Link> and
            its score shows up here, so you can see yourself improve.
          </p>
        </div>
      ) : (
        <>
          <div className="card">
            <h3 className="pg-card-title">Practice scores over time</h3>
            <p className="hint" style={{ margin: "2px 0 8px" }}>
              Each dot is a finished session, scored out of 100.
              {p.best_score !== null && ` Best so far: ${p.best_score}.`}
            </p>
            {p.scores.length > 0
              ? <ScoreChart points={p.scores} />
              : <p className="hint">Sessions are scored when you press End session in the coach.</p>}
          </div>

          <div className="pg-two">
            <div className="card">
              <h3 className="pg-card-title">By target role</h3>
              <ul className="pg-list">
                {p.by_role.map((r) => (
                  <li key={r.target_role}>
                    <div>
                      <strong>{r.target_role}</strong>
                      <span className="hint">{r.sessions} session{r.sessions === 1 ? "" : "s"}</span>
                    </div>
                    <div className="pg-list-right">
                      {r.first_score !== null && r.latest_score !== null && r.scored >= 2
                        ? <>{r.first_score} to {r.latest_score}
                            <span className={r.change! > 0 ? "pg-up" : r.change! < 0 ? "pg-down" : ""}>
                              {r.change! > 0 ? ` (up ${r.change})` : r.change! < 0 ? ` (down ${-r.change!})` : " (no change)"}
                            </span></>
                        : r.latest_score !== null ? `Score ${r.latest_score}` : <span className="hint">Not scored yet</span>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
            <div className="card">
              <h3 className="pg-card-title">Where to focus next</h3>
              {p.weakest_topics.length === 0 ? (
                <p className="hint" style={{ margin: 0 }}>Topics show here once your sessions are scored.</p>
              ) : (
                <ul className="pg-list">
                  {p.weakest_topics.map((t) => (
                    <li key={t.topic}>
                      <div><strong>{t.topic}</strong><span className="hint">{t.sessions} session{t.sessions === 1 ? "" : "s"}</span></div>
                      <div className="pg-list-right">Average {Math.round(t.avg_score)}</div>
                    </li>
                  ))}
                </ul>
              )}
              <p className="hint" style={{ margin: "12px 0 0" }}>
                Your lowest-scoring topics so far. Another session on one of them is the quickest way to move your average.
                {" "}
                {p.notes_saved > 0
                  ? <>You have saved {p.notes_saved} study note{p.notes_saved === 1 ? "" : "s"}. <Link href="/dashboard/career-coach/study">Review them</Link>.</>
                  : <>Save coach replies to a <Link href="/dashboard/career-coach/study">study folder</Link> to review later.</>}
              </p>
            </div>
          </div>
        </>
      )}

      <h2 className="pg-h2">Job search</h2>
      {!hasJobs ? (
        <div className="card">
          <p style={{ margin: 0 }}>
            No matches yet. Set up a <Link href="/dashboard/profiles">search profile</Link> and run a search, then your funnel appears here.
          </p>
        </div>
      ) : (
        <div className="card">
          <h3 className="pg-card-title">Your funnel</h3>
          <p className="hint" style={{ margin: "2px 0 10px" }}>
            Where your applications stand today. Applications that moved on to a later stage count in the earlier ones too.
          </p>
          <Funnel funnel={f} />
        </div>
      )}

      {js.weeks.some((w) => w.matches + w.applied + w.practice > 0) && (
        <div className="card">
          <h3 className="pg-card-title">Last 8 weeks</h3>
          <p className="hint" style={{ margin: "2px 0 8px" }}>Weeks start on Monday.</p>
          <WeekChart weeks={js.weeks} />
        </div>
      )}
    </div>
  );
}
