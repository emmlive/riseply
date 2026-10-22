"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, CoachCourseListItem } from "@/lib/api";

// "Continue your course": the newest Career Coach course that still has a
// module to go. Shows nothing when there is none, or while loading.
export default function CourseProgress() {
  const [course, setCourse] = useState<CoachCourseListItem | null>(null);
  useEffect(() => {
    api<CoachCourseListItem[]>("/career-coach/courses")
      .then((rows) => setCourse(rows.find((c) => c.modules > 0 && c.done < c.modules) ?? null))
      .catch(() => {});
  }, []);
  if (!course) return null;
  const pct = Math.round((course.done / course.modules) * 100);
  return (
    <div className="card cpg-card">
      <div className="card-row" style={{ alignItems: "center" }}>
        <div style={{ minWidth: 0 }}>
          <h3 style={{ margin: "0 0 2px" }}>Continue your course</h3>
          <p style={{ margin: 0 }}><strong>{course.title}</strong></p>
          <p className="hint" style={{ margin: "2px 0 0" }}>
            {course.done === 0 ? "Not started" : `${course.done} of ${course.modules} modules done`}
            {course.next_module ? ` · Next: ${course.next_module}` : ""}
          </p>
        </div>
        <Link className="btn btn-primary btn-sm" href={`/dashboard/career-coach?course=${course.id}`}>
          {course.done === 0 ? "Start" : "Continue"}
        </Link>
      </div>
      <div className="cpg-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Course progress">
        <div style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
