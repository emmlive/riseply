"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchProgress, ProgressData } from "@/lib/api";

// A one-line summary for the Overview page, linking to the full Progress page.
export default function ProgressGlance() {
  const [d, setD] = useState<ProgressData | null>(null);
  useEffect(() => { fetchProgress().then(setD).catch(() => {}); }, []);
  if (!d) return null;
  const p = d.practice, f = d.job_search.funnel;
  if (p.sessions_completed === 0 && f.matched === 0) return null;
  const bits: string[] = [];
  if (p.avg_score !== null) bits.push(`Average practice score ${Math.round(p.avg_score)}`);
  else if (p.sessions_completed) bits.push(`${p.sessions_completed} practice session${p.sessions_completed === 1 ? "" : "s"} finished`);
  if (f.matched) bits.push(`${f.applied} of ${f.matched} matches applied to`);
  if (f.interviewing) bits.push(`${f.interviewing} interview${f.interviewing === 1 ? "" : "s"}`);
  return (
    <div className="card pg-glance">
      <div>
        <h3 style={{ margin: 0 }}>Your progress</h3>
        <p className="hint" style={{ margin: "4px 0 0" }}>{bits.join(". ")}.</p>
      </div>
      <Link href="/dashboard/progress" className="btn btn-ghost btn-sm">See progress</Link>
    </div>
  );
}
