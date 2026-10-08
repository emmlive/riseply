"use client";

import { useEffect, useRef, useState } from "react";
import { api, downloadFile, ResumeBlock, ResumePreviewData } from "@/lib/api";

// Shows a tailored resume as a page, before the person downloads it, and
// lets them edit it. Content comes from the stored .docx
// (GET .../tailored-resume/preview); saving rebuilds that same .docx
// (PUT .../tailored-resume), so Download always matches what's on screen.

type Draft = ResumeBlock & { uid: number };

const ADDABLE: { label: string; make: () => ResumeBlock }[] = [
  { label: "Section", make: () => ({ type: "heading", text: "" }) },
  { label: "Role or degree", make: () => ({ type: "entry", left: "", right: "" }) },
  { label: "Skills line", make: () => ({ type: "skills", label: "", text: "" }) },
  { label: "Paragraph", make: () => ({ type: "text", text: "" }) },
];

const PLACEHOLDERS: Record<string, string> = {
  name: "Full name",
  headline: "Headline",
  contact: "Email  |  Phone  |  City, ST",
  heading: "Section title",
  sub: "Company — Location",
  bullet: "Describe what you did and the result",
  text: "Text",
};

let uidCounter = 0;
const withUid = (b: ResumeBlock): Draft => ({ ...b, uid: ++uidCounter });
const stripUid = ({ uid: _uid, ...rest }: Draft): ResumeBlock => rest as ResumeBlock;

export default function ResumePreview({
  applicationId,
  company,
  onClose,
  onSaved,
}: {
  applicationId: number;
  company: string;
  onClose: () => void;
  onSaved?: () => void;
}) {
  const [data, setData] = useState<ResumePreviewData | null>(null);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft[]>([]);
  const [saving, setSaving] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  const dirty = editing && data !== null &&
    JSON.stringify(draft.map(stripUid)) !== JSON.stringify(data.blocks);

  useEffect(() => {
    let cancelled = false;
    api<ResumePreviewData>(`/applications/${applicationId}/tailored-resume/preview`)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e?.message || "We couldn't load this preview. You can still download the resume."); });
    return () => { cancelled = true; };
  }, [applicationId]);

  function requestClose() {
    if (dirty && !window.confirm("Close without saving? Your edits will be lost.")) return;
    onClose();
  }

  useEffect(() => {
    closeRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previousOverflow; };
  }, []);

  // Escape closes, but never silently throws away unsaved edits.
  const requestCloseRef = useRef(requestClose);
  requestCloseRef.current = requestClose;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") requestCloseRef.current(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  async function download() {
    setDownloading(true);
    setError("");
    try {
      await downloadFile(`/applications/${applicationId}/tailored-resume`, data?.filename || "tailored_resume.docx");
    } catch (e: any) {
      setError(e?.message || "Couldn't download that file.");
    } finally {
      setDownloading(false);
    }
  }

  function startEditing() {
    if (!data) return;
    setError("");
    setDraft(data.blocks.map(withUid));
    setEditing(true);
  }

  function cancelEditing() {
    if (dirty && !window.confirm("Discard your edits?")) return;
    setEditing(false);
    setError("");
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      const updated = await api<ResumePreviewData>(`/applications/${applicationId}/tailored-resume`, {
        method: "PUT",
        body: JSON.stringify({ blocks: draft.map(stripUid) }),
      });
      setData(updated);
      setEditing(false);
      onSaved?.();
    } catch (e: any) {
      setError(e?.message || "We couldn't save your changes. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  const update = (uid: number, patch: Partial<Draft>) =>
    setDraft((rows) => rows.map((r) => (r.uid === uid ? ({ ...r, ...patch } as Draft) : r)));
  const remove = (uid: number) => setDraft((rows) => rows.filter((r) => r.uid !== uid));
  const move = (uid: number, delta: number) =>
    setDraft((rows) => {
      const i = rows.findIndex((r) => r.uid === uid);
      const j = i + delta;
      if (i < 0 || j < 0 || j >= rows.length) return rows;
      const next = rows.slice();
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  const insertBulletAfter = (uid: number) =>
    setDraft((rows) => {
      let i = rows.findIndex((r) => r.uid === uid);
      // A role's company line sits right under it; bullets go below that.
      if (rows[i]?.type === "entry" && rows[i + 1]?.type === "sub") i += 1;
      const next = rows.slice();
      next.splice(i + 1, 0, withUid({ type: "bullet", text: "" }));
      return next;
    });
  const append = (b: ResumeBlock) => setDraft((rows) => [...rows, withUid(b)]);

  return (
    <div className="rp-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) requestClose(); }}>
      <div className="rp-dialog" role="dialog" aria-modal="true" aria-label={`Tailored resume for ${company}`}>
        <header className="rp-head">
          <div>
            <h2 className="rp-title">{editing ? "Edit resume" : "Tailored resume"}</h2>
            <p className="hint">
              {editing
                ? "Change any line, add or remove bullets, sections and roles. Save to update the Word file."
                : `For ${company}. Check it over, edit anything, then download the Word file.`}
            </p>
          </div>
          <div className="rp-actions">
            {editing ? (
              <>
                <button className="btn btn-primary btn-sm" onClick={save} disabled={saving || !dirty}>
                  {saving ? "Saving…" : "Save changes"}
                </button>
                <button className="btn btn-ghost btn-sm" onClick={cancelEditing} disabled={saving}>Cancel</button>
              </>
            ) : (
              <>
                <button className="btn btn-ghost btn-sm" onClick={startEditing} disabled={!data}>Edit</button>
                <button className="btn btn-primary btn-sm" onClick={download} disabled={downloading || !data}>
                  {downloading ? "Downloading…" : "Download .docx"}
                </button>
                <button ref={closeRef} className="btn btn-ghost btn-sm" onClick={requestClose}>Close</button>
              </>
            )}
          </div>
        </header>

        <div className="rp-body">
          {error && <p className="cc-error" role="alert">{error}</p>}
          {!data && !error && <p className="hint">Loading preview…</p>}
          {data && !editing && (
            <>
              {data.rationale && (
                <div className="brief rp-why"><strong>What we changed:</strong> {data.rationale}</div>
              )}
              <article className="rp-paper" aria-label="Resume preview">
                {data.blocks.map((b, i) => <Block key={i} block={b} />)}
              </article>
            </>
          )}
          {data && editing && (
            <>
              <article className="rp-paper rp-editing" aria-label="Resume editor">
                {draft.map((row, i) => (
                  <EditRow
                    key={row.uid}
                    row={row}
                    isFirst={i === 0}
                    isLast={i === draft.length - 1}
                    onChange={(patch) => update(row.uid, patch)}
                    onRemove={() => remove(row.uid)}
                    onMove={(d) => move(row.uid, d)}
                    onAddBullet={() => insertBulletAfter(row.uid)}
                  />
                ))}
              </article>
              <div className="rp-add" role="group" aria-label="Add to resume">
                <span className="hint">Add:</span>
                {ADDABLE.map((a) => (
                  <button key={a.label} className="btn btn-ghost btn-sm" onClick={() => append(a.make())}>
                    + {a.label}
                  </button>
                ))}
                <span className="hint">New items go at the bottom. Use ↑ ↓ to move them.</span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Block({ block }: { block: ResumeBlock }) {
  switch (block.type) {
    case "name": return <h3 className="rp-name">{block.text}</h3>;
    case "headline": return <p className="rp-headline">{block.text}</p>;
    case "contact": return <p className="rp-contact">{block.text}</p>;
    case "heading": return <h4 className="rp-heading">{block.text}</h4>;
    case "entry":
      return (
        <div className="rp-entry">
          <strong>{block.left}</strong>
          {block.right && <span>{block.right}</span>}
        </div>
      );
    case "sub": return <p className="rp-sub">{block.text}</p>;
    case "bullet": return <p className="rp-bullet">{block.text}</p>;
    case "skills":
      return <p className="rp-skills">{block.label && <strong>{block.label}: </strong>}{block.text}</p>;
    default: return <p className="rp-text">{block.text}</p>;
  }
}

// A textarea that grows with its content.
function AutoText({ value, onChange, placeholder, label, className }: {
  value: string; onChange: (v: string) => void; placeholder?: string; label: string; className?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (el) { el.style.height = "auto"; el.style.height = `${el.scrollHeight}px`; }
  }, [value]);
  return (
    <textarea
      ref={ref}
      rows={1}
      className={`rp-input ${className || ""}`}
      value={value}
      placeholder={placeholder}
      aria-label={label}
      onChange={(e) => onChange(e.target.value.replace(/\n/g, " "))}
    />
  );
}

function EditRow({ row, isFirst, isLast, onChange, onRemove, onMove, onAddBullet }: {
  row: Draft; isFirst: boolean; isLast: boolean;
  onChange: (patch: Partial<Draft>) => void; onRemove: () => void;
  onMove: (delta: number) => void; onAddBullet: () => void;
}) {
  const canAddBullet = row.type === "entry" || row.type === "sub" || row.type === "bullet";
  const typeName = row.type === "entry" ? "role" : row.type === "skills" ? "skills line" : row.type;

  return (
    <div className={`rp-row rp-row-${row.type}`}>
      <div className="rp-fields">
        {row.type === "entry" ? (
          <>
            <AutoText className="rp-in-entry" label="Role or degree" placeholder="Job title or degree"
              value={row.left} onChange={(v) => onChange({ left: v } as Partial<Draft>)} />
            <AutoText className="rp-in-dates" label="Dates" placeholder="2020 – Present"
              value={row.right} onChange={(v) => onChange({ right: v } as Partial<Draft>)} />
          </>
        ) : row.type === "skills" ? (
          <>
            <AutoText className="rp-in-label" label="Skills category" placeholder="Category"
              value={row.label} onChange={(v) => onChange({ label: v } as Partial<Draft>)} />
            <AutoText className="rp-in-skills" label="Skills" placeholder="Skill, skill, skill"
              value={row.text} onChange={(v) => onChange({ text: v } as Partial<Draft>)} />
          </>
        ) : (
          <AutoText className={`rp-in-${row.type}`} label={`${typeName} text`} placeholder={PLACEHOLDERS[row.type]}
            value={row.text} onChange={(v) => onChange({ text: v } as Partial<Draft>)} />
        )}
      </div>
      <div className="rp-tools">
        <button type="button" onClick={() => onMove(-1)} disabled={isFirst} aria-label={`Move ${typeName} up`} title="Move up">↑</button>
        <button type="button" onClick={() => onMove(1)} disabled={isLast} aria-label={`Move ${typeName} down`} title="Move down">↓</button>
        {canAddBullet && (
          <button type="button" onClick={onAddBullet} aria-label="Add a bullet below" title="Add a bullet below">+ bullet</button>
        )}
        <button type="button" className="rp-del" onClick={onRemove} aria-label={`Remove ${typeName}`} title="Remove">✕</button>
      </div>
    </div>
  );
}
