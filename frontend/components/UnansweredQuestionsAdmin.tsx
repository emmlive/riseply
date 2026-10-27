"use client";

import { useEffect, useState } from "react";
import { api, formatWhen } from "@/lib/api";

interface Row { question: string; people: number; times_seen: number; sample_site: string; last_seen: string | null }

// Admin: the questions Autofill couldn't answer, counted across people (no
// names or emails), most common first. What to support next.
export default function UnansweredQuestionsAdmin() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<Row[]>("/admin/unanswered-questions").then(setRows).catch((e) => setError(e?.message || "Couldn't load the questions."));
  }, []);
  if (error) return <p className="error">{error}</p>;
  if (!rows) return <p className="muted">Loading…</p>;
  if (!rows.length) return <p className="muted">No unanswered questions yet. They appear here after people use Autofill on application forms.</p>;
  return (
    <div>
      <p className="muted" style={{ marginTop: 0 }}>Questions Autofill left for people, most common first. Counts only; no names or emails. Add the common ones to the standard answers.</p>
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr style={{ textAlign: "left" }}><th style={{ padding: 10 }}>Question</th><th>People</th><th>Times</th><th>Example site</th><th>Last seen</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.question} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: 10 }}>{r.question}</td>
                <td>{r.people}</td><td>{r.times_seen}</td><td>{r.sample_site}</td>
                <td>{r.last_seen ? formatWhen(r.last_seen) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
