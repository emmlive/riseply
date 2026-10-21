"use client";

import { useEffect, useState } from "react";
import { api, downloadFile, TaskGuide, TaskGuideListItem, TaskGuideStep } from "@/lib/api";
import MiniMarkdown, { hasTable } from "@/components/MiniMarkdown";

// "I was given this task and don't know where to start." Paste the task and
// get a plan: what to confirm, what you need, templates to fill in, ordered
// steps, and a quality check. You do the work; the guide reviews what you
// write and answers questions on any step. Works for any field.

type Turn = { role: "user" | "assistant"; content: string };

const LEVELS = [
  { value: "first_time", label: "I've never done this" },
  { value: "some_experience", label: "I've done something similar" },
  { value: "experienced", label: "I know this field well" },
];

function closeMenu(e: React.MouseEvent) {
  (e.currentTarget as HTMLElement).closest("details")?.removeAttribute("open");
}

// One template: a formatted preview, plus Copy and a Download menu.
function Material({ guide, index }: { guide: TaskGuide; index: number }) {
  const m = guide.materials[index];
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");

  async function get(format: string, e: React.MouseEvent) {
    closeMenu(e);
    setNote("");
    try {
      await downloadFile(`/task-guides/${guide.id}/materials/${index}/export?format=${format}`, `${m.name}.${format}`);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Couldn't create that file.");
    }
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(m.template);
      setNote("Copied.");
    } catch {
      setNote("Couldn't copy. Select the text and copy it yourself.");
    }
  }

  return (
    <div className="card tg-mat">
      <h3 style={{ margin: 0 }}>{m.name}</h3>
      {m.purpose && <p className="muted" style={{ margin: "4px 0 0" }}>{m.purpose}</p>}
      <div className={`tg-doc${open ? " tg-open" : ""}`}><MiniMarkdown text={m.template} /></div>
      <div className="tg-actions">
        <details className="tg-menu">
          <summary className="btn btn-primary">Download</summary>
          <div className="tg-menu-list">
            <button onClick={(e) => get("docx", e)}>Word document (.docx)</button>
            <button onClick={(e) => get("pdf", e)}>PDF</button>
            {hasTable(m.template) && <button onClick={(e) => get("xlsx", e)}>Excel spreadsheet (.xlsx)</button>}
            <button onClick={(e) => get("md", e)}>Plain text (.md)</button>
          </div>
        </details>
        <button className="btn" onClick={copy}>Copy</button>
        <button className="btn" onClick={() => setOpen(!open)}>{open ? "Show less" : "Show all"}</button>
      </div>
      {note && <p className="tg-note" role="status">{note}</p>}
    </div>
  );
}

// Download or share the steps: files, the phone/computer share sheet, email.
function StepsActions({ guide }: { guide: TaskGuide }) {
  const [withTemplates, setWithTemplates] = useState(false);
  const [note, setNote] = useState("");

  async function get(format: string, e: React.MouseEvent) {
    closeMenu(e);
    setNote("");
    try {
      await downloadFile(`/task-guides/${guide.id}/export?format=${format}&include_templates=${withTemplates}`, `${guide.title}.${format}`);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Couldn't create that file.");
    }
  }
  async function text(): Promise<string> {
    return (await api<{ text: string }>(`/task-guides/${guide.id}/share-text`)).text;
  }
  async function copy(e: React.MouseEvent) {
    closeMenu(e);
    try {
      await navigator.clipboard.writeText(await text());
      setNote("Steps copied. Paste them into a message, chat or notes app.");
    } catch {
      setNote("Couldn't copy. Try the download instead.");
    }
  }
  async function email(e: React.MouseEvent) {
    closeMenu(e);
    try {
      const body = (await text()).slice(0, 1800);
      window.location.href = `mailto:?subject=${encodeURIComponent(guide.title)}&body=${encodeURIComponent(body)}`;
    } catch {
      setNote("Couldn't prepare the email. Try copying the steps.");
    }
  }
  async function share(e: React.MouseEvent) {
    closeMenu(e);
    try {
      await navigator.share({ title: guide.title, text: await text() });
    } catch (err) {
      if ((err as Error)?.name !== "AbortError") setNote("Couldn't open sharing. Try Copy or Email.");
    }
  }
  const canShare = typeof navigator !== "undefined" && typeof navigator.share === "function";

  return (
    <>
      <div className="tg-actions" style={{ marginTop: 12, marginBottom: 4 }}>
        <details className="tg-menu">
          <summary className="btn btn-primary">Download steps</summary>
          <div className="tg-menu-list">
            <button onClick={(e) => get("docx", e)}>Word document (.docx)</button>
            <button onClick={(e) => get("pdf", e)}>PDF</button>
            <button onClick={(e) => get("md", e)}>Plain text (.md)</button>
            <label><input type="checkbox" checked={withTemplates} onChange={(e) => setWithTemplates(e.target.checked)} /> Include the templates</label>
          </div>
        </details>
        <details className="tg-menu">
          <summary className="btn">Share</summary>
          <div className="tg-menu-list">
            {canShare && <button onClick={share}>Share with an app…</button>}
            <button onClick={email}>Email the steps</button>
            <button onClick={copy}>Copy steps as text</button>
          </div>
        </details>
        <button className="btn" onClick={() => window.print()}>Print</button>
      </div>
      {note && <p className="tg-note" role="status">{note}</p>}
    </>
  );
}

function StepCard({ guide, step, done, onToggle }: { guide: TaskGuide; step: TaskGuideStep; done: boolean; onToggle: () => void }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function ask() {
    const message = text.trim();
    if (busy || message.length < 2) return;
    setBusy(true);
    setError("");
    try {
      const r = await api<{ reply: string }>(`/task-guides/${guide.id}/help`, {
        method: "POST",
        body: JSON.stringify({ step_id: step.id, message, history: turns }),
      });
      setTurns([...turns, { role: "user", content: message }, { role: "assistant", content: r.reply }]);
      setText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`card tg-step${done ? " tg-done" : ""}`}>
      <input type="checkbox" checked={done} onChange={onToggle} aria-label={`Mark "${step.title}" done`} />
      <div className="tg-step-body">
        <h3 style={{ margin: 0 }}>
          {step.title} {step.minutes > 0 && <span className="sg-badge">about {step.minutes} min</span>}
        </h3>
        <p>{step.what_to_do}</p>
        {step.how && <p><span className="tg-label">How: </span>{step.how}</p>}
        {step.done_when && <p><span className="tg-label">Done when: </span>{step.done_when}</p>}
        {step.watch_out && <p className="tg-watch">Watch out: {step.watch_out}</p>}
        <button className="btn" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "Hide help" : "Ask a question or check my work"}
        </button>
        {open && (
          <div className="tg-help">
            {turns.map((t, i) => (
              <div key={i} className={`tg-turn ${t.role === "user" ? "tg-me" : "tg-ai"}`}>{t.content}</div>
            ))}
            <textarea
              value={text} maxLength={6000} onChange={(e) => setText(e.target.value)}
              placeholder="Ask anything about this step, or paste what you've written and ask for a review."
              aria-label={`Question about ${step.title}`}
            />
            <p style={{ margin: "8px 0 0" }}>
              <button className="btn btn-primary" onClick={ask} disabled={busy || text.trim().length < 2}>
                {busy ? "Thinking…" : "Send"}
              </button>
            </p>
            {error && <p className="cc-error" role="alert">{error}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

export default function TaskGuidePage() {
  const [task, setTask] = useState("");
  const [role, setRole] = useState("");
  const [level, setLevel] = useState("some_experience");
  const [list, setList] = useState<TaskGuideListItem[]>([]);
  const [guide, setGuide] = useState<TaskGuide | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function refresh() {
    api<TaskGuideListItem[]>("/task-guides").then(setList).catch(() => {});
  }
  useEffect(refresh, []);

  async function build() {
    if (busy || task.trim().length < 15) return;
    setBusy(true);
    setError("");
    try {
      const g = await api<TaskGuide>("/task-guides", {
        method: "POST",
        body: JSON.stringify({ task: task.trim(), role: role.trim(), level }),
      });
      setGuide(g);
      setTask("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function open(id: number) {
    setError("");
    try {
      setGuide(await api<TaskGuide>(`/task-guides/${id}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't open that guide.");
    }
  }

  async function toggle(stepId: string) {
    if (!guide) return;
    const done = guide.done.includes(stepId) ? guide.done.filter((d) => d !== stepId) : [...guide.done, stepId];
    setGuide({ ...guide, done });
    try {
      const g = await api<TaskGuide>(`/task-guides/${guide.id}/progress`, { method: "PUT", body: JSON.stringify({ done }) });
      setGuide((cur) => (cur && cur.id === g.id ? { ...cur, done: g.done } : cur));
      refresh();
    } catch {
      setError("Couldn't save your progress. Check your connection.");
    }
  }

  async function remove() {
    if (!guide || !window.confirm("Delete this guide?")) return;
    try {
      await api(`/task-guides/${guide.id}`, { method: "DELETE" });
      setGuide(null);
      refresh();
    } catch {
      setError("Couldn't delete it. Try again.");
    }
  }

  const pct = guide && guide.steps.length ? Math.round((guide.done.length / guide.steps.length) * 100) : 0;

  return (
    <div>
      <h1>Task guide</h1>
      <p className="muted">
        Paste the task you were given. You&apos;ll get what to confirm with whoever assigned it, what you need, templates to
        fill in, and the steps in order. You do the work; the guide checks it and answers questions on any step.
      </p>

      <div className="card tg-form">
        <label className="cc-label" htmlFor="tg-task">The task, as it was given to you</label>
        <textarea
          id="tg-task" value={task} maxLength={4000} onChange={(e) => setTask(e.target.value)}
          placeholder="e.g. Put together the monthly vendor payment reconciliation and flag anything that doesn't match by Friday."
        />
        <div className="tg-opts">
          <label>
            <span className="cc-label">Your role (optional)</span>
            <input value={role} maxLength={120} onChange={(e) => setRole(e.target.value)} placeholder="e.g. Accounts payable clerk" />
          </label>
          <label>
            <span className="cc-label">How familiar is this?</span>
            <select value={level} onChange={(e) => setLevel(e.target.value)}>
              {LEVELS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
            </select>
          </label>
          <button className="btn btn-primary" onClick={build} disabled={busy || task.trim().length < 15}>
            {busy ? "Building your guide…" : "Build my guide"}
          </button>
        </div>
        {busy && <p className="muted" style={{ marginBottom: 0 }}>This takes about a minute.</p>}
        {error && <p className="cc-error" role="alert">{error}</p>}
      </div>

      {list.length > 0 && (
        <>
          <h2>Your guides</h2>
          <ul className="tg-recent">
            {list.map((g) => (
              <li key={g.id}>
                <button onClick={() => open(g.id)} aria-current={guide?.id === g.id}>
                  {g.title}<span className="tg-n">{g.done}/{g.steps}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {guide && (
        <>
          <div className="card">
            <h2 style={{ marginTop: 0 }}>{guide.title}</h2>
            <p>{guide.goal}</p>
            {guide.deliverable && <p><span className="tg-label">You hand in: </span>{guide.deliverable}</p>}
            {guide.why_it_matters && <p className="tg-why">{guide.why_it_matters}</p>}
            {guide.total_time && <p><span className="tg-label">Time: </span>{guide.total_time}</p>}
            <div className="tg-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Steps finished">
              <span style={{ width: `${pct}%` }} />
            </div>
            <p className="muted" style={{ margin: 0 }}>{guide.done.length} of {guide.steps.length} steps done</p>
            <StepsActions guide={guide} />
            <p style={{ margin: "12px 0 0" }}><button className="btn" onClick={remove}>Delete this guide</button></p>
          </div>

          <div className="tg-two" style={{ margin: "16px 0" }}>
            {guide.confirm_first.length > 0 && (
              <div className="card">
                <h3 style={{ marginTop: 0 }}>Ask before you start</h3>
                <ul className="tg-list">{guide.confirm_first.map((q, i) => <li key={i}>{q}</li>)}</ul>
              </div>
            )}
            {guide.requirements.length > 0 && (
              <div className="card">
                <h3 style={{ marginTop: 0 }}>What you&apos;ll need</h3>
                <ul className="tg-list">
                  {guide.requirements.map((r, i) => (
                    <li key={i}>{r.item}{r.why && <span className="tg-why"> — {r.why}</span>}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {guide.materials.length > 0 && (
            <>
              <h2>Templates and documents</h2>
              {guide.materials.map((m, i) => <Material key={`${guide.id}-m${i}`} guide={guide} index={i} />)}
            </>
          )}

          <h2>Steps</h2>
          <div style={{ margin: "-4px 0 14px" }}><StepsActions guide={guide} /></div>
          {guide.steps.map((s) => (
            <StepCard key={`${guide.id}-${s.id}`} guide={guide} step={s} done={guide.done.includes(s.id)} onToggle={() => toggle(s.id)} />
          ))}

          <div style={{ margin: "4px 0 0" }}><StepsActions guide={guide} /></div>

          <div className="tg-two" style={{ margin: "16px 0" }}>
            {guide.quality_check.length > 0 && (
              <div className="card">
                <h3 style={{ marginTop: 0 }}>Check before you hand it in</h3>
                <ul className="tg-list">{guide.quality_check.map((q, i) => <li key={i}>{q}</li>)}</ul>
              </div>
            )}
            {guide.common_mistakes.length > 0 && (
              <div className="card">
                <h3 style={{ marginTop: 0 }}>Common mistakes</h3>
                <ul className="tg-list">{guide.common_mistakes.map((q, i) => <li key={i}>{q}</li>)}</ul>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
