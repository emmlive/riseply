"use client";

import { useEffect, useState } from "react";
import { api, type CoachNotebook as Notebook } from "@/lib/api";
import Fold from "@/components/Fold";

const KIND: Record<string, string> = {
  strong: "Got it", shaky: "Still shaky", style: "How you learn", goal: "Goal", homework: "Homework",
};

// "What your coach remembers": the short notes the coach keeps between
// sessions. Nothing here is hidden: the person can read each note, delete one,
// clear them all, or turn remembering off.
export default function CoachNotebook() {
  const [nb, setNb] = useState<Notebook | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Notebook>("/career-coach/notebook").then(setNb).catch(() => setNb(null));
  }, []);

  async function run(path: string, init: RequestInit) {
    setError("");
    try {
      setNb(await api<Notebook>(path, init));
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't save. Try again.");
    }
  }

  if (!nb) return null;
  return (
    <Fold id="notebook" title="What your coach remembers" defaultOpen={false} note={nb.enabled ? (nb.items.length ? `${nb.items.length}` : undefined) : "Off"}>
      <div className="cc-notebook">
        <p className="hint" style={{ marginTop: 0 }}>
          After a learning session your coach jots a few notes on what clicked, what is still shaky and how you like things explained, so the next session starts where you stopped. Interviews and negotiation role-plays never use them.
        </p>
        {nb.items.length === 0 ? (
          <p className="cc-empty">{nb.enabled ? "Nothing yet. Notes appear after you finish a session." : "Remembering is off, so nothing is being saved."}</p>
        ) : (
          <ul>
            {nb.items.map((i) => (
              <li key={i.id}>
                <div>
                  <span className="kind">{KIND[i.kind] ?? i.kind}{i.topic ? ` · ${i.topic}` : ""}</span>
                  {i.text}
                </div>
                <button className="btn btn-ghost btn-sm" aria-label={`Delete note: ${i.text}`} onClick={() => run(`/career-coach/notebook/${i.id}`, { method: "DELETE" })}>Delete</button>
              </li>
            ))}
          </ul>
        )}
        <div className="row">
          <button className="btn btn-ghost btn-sm" onClick={() => run("/career-coach/notebook", { method: "PUT", body: JSON.stringify({ enabled: !nb.enabled }) })}>
            {nb.enabled ? "Stop remembering" : "Turn remembering on"}
          </button>
          {nb.items.length > 0 && (
            <button className="btn btn-ghost btn-sm" onClick={() => run("/career-coach/notebook", { method: "DELETE" })}>Clear all</button>
          )}
        </div>
        {error && <p className="hint" role="alert">{error}</p>}
      </div>
    </Fold>
  );
}
