"use client";

import { CoachCourse } from "@/lib/api";
import { minutesText } from "@/lib/sessionClock";

// The syllabus: what the course covers, then its modules in order. Each
// module is one class with the coach; finished ones keep their recap.
export default function CoursePanel({ course, busyModule, onStart, onOpen, onClose, onDelete, onArchive }: {
  course: CoachCourse;
  busyModule: string;
  onStart: (moduleId: string) => void;
  onOpen: (sessionId: number) => void;
  onClose: () => void;
  onDelete: () => void;
  onArchive?: () => void;
}) {
  const nextId = course.modules.find((m) => !m.done)?.id;
  const spent = course.modules.reduce((n, m) => n + (m.spent_seconds || 0), 0);
  const planned = course.modules.reduce((n, m) => n + m.minutes, 0);
  return (
    <div className="card cp-course">
      <div className="cp-course-head">
        <div>
          <h2 className="cc-card-title">{course.title}</h2>
          <p className="muted" style={{ margin: 0 }}>
            {course.target_role} · {course.modules.length} modules · about {course.total_hours} hours · {course.done} of {course.modules.length} done{spent > 0 ? ` · ${minutesText(spent)} of ${planned} min spent` : ""}
          </p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>Back</button>
      </div>
      {course.overview && <p>{course.overview}</p>}
      <div className="cp-course-cols">
        {course.outcomes.length > 0 && (
          <div><h4>You will be able to</h4><ul>{course.outcomes.map((o) => <li key={o}>{o}</li>)}</ul></div>
        )}
        {course.prerequisites.length > 0 && (
          <div><h4>Before you start</h4><ul>{course.prerequisites.map((o) => <li key={o}>{o}</li>)}</ul></div>
        )}
      </div>

      <h3 className="cp-syllabus-title">Syllabus</h3>
      <ol className="cp-modules">
        {course.modules.map((m, i) => (
          <li key={m.id} className={`cp-module ${m.done ? "is-done" : ""} ${m.id === nextId ? "is-next" : ""}`}>
            <div className="cp-module-top">
              <span className="cp-module-n" aria-hidden>{m.done ? "✓" : i + 1}</span>
              <div className="cp-module-title">
                <strong>{m.title}</strong>
                <span className="muted"> · {m.minutes} min{m.spent_seconds > 0 ? ` · ${minutesText(m.spent_seconds)} spent` : ""}</span>
              </div>
            </div>
            {m.summary && <p className="cp-module-sum">{m.summary}</p>}
            <ul className="cp-objectives">{m.objectives.map((o) => <li key={o}>{o}</li>)}</ul>
            {(m.hands_on || m.checkpoint) && (
              <p className="muted cp-module-extra">
                {m.hands_on && <>Hands-on: {m.hands_on} </>}
                {m.checkpoint && <>Checkpoint: {m.checkpoint}</>}
              </p>
            )}
            <div className="cp-module-actions">
              {m.session_id && m.session_status === "in_progress" && !m.done && (
                <button className="btn btn-primary btn-sm" onClick={() => onOpen(m.session_id!)}>Continue module</button>
              )}
              {(!m.session_id || (m.session_status === "completed" && !m.done)) && (
                <button className={m.id === nextId ? "btn btn-primary btn-sm" : "btn btn-ghost btn-sm"}
                        onClick={() => onStart(m.id)} disabled={busyModule !== ""}>
                  {busyModule === m.id ? "Starting…" : `Start module · ${m.minutes} min timer`}
                </button>
              )}
              {m.done && m.session_id && (
                <>
                  <button className="btn btn-ghost btn-sm" onClick={() => onOpen(m.session_id!)}>Review lesson and recap</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => onStart(m.id)} disabled={busyModule !== ""}>Retake · {m.minutes} min timer</button>
                </>
              )}
            </div>
          </li>
        ))}
      </ol>
      <p className="muted" style={{ margin: "12px 0 0", fontSize: "0.82rem" }}>
        Each module has its own timer, set to its length. You can pause, stop or change it from inside the module. Every module starts from the basics, whatever your resume says. {onArchive && <><button className="sg-link" onClick={onArchive}>Archive this course</button>{" · "}</>}<button className="sg-link" onClick={onDelete}>Delete this course</button>
      </p>
    </div>
  );
}
