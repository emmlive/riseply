"use client";

import { useEffect, useRef, useState } from "react";
import { api, downloadFile, ResumeBlock, ResumePreviewData } from "@/lib/api";

// Shows a tailored resume as a page, before the person downloads it. The
// content comes from the stored .docx itself (GET .../tailored-resume/preview),
// so the preview always matches what the download contains.
export default function ResumePreview({
  applicationId,
  company,
  onClose,
}: {
  applicationId: number;
  company: string;
  onClose: () => void;
}) {
  const [data, setData] = useState<ResumePreviewData | null>(null);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let cancelled = false;
    api<ResumePreviewData>(`/applications/${applicationId}/tailored-resume/preview`)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e?.message || "We couldn't load this preview. You can still download the resume."); });
    return () => { cancelled = true; };
  }, [applicationId]);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  async function download() {
    setDownloading(true);
    try {
      await downloadFile(`/applications/${applicationId}/tailored-resume`, data?.filename || "tailored_resume.docx");
    } catch (e: any) {
      setError(e?.message || "Couldn't download that file.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="rp-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="rp-dialog" role="dialog" aria-modal="true" aria-label={`Tailored resume for ${company}`}>
        <header className="rp-head">
          <div>
            <h2 className="rp-title">Tailored resume</h2>
            <p className="hint">For {company}. Check it over, then download the Word file.</p>
          </div>
          <div className="rp-actions">
            <button className="btn btn-primary btn-sm" onClick={download} disabled={downloading || !data}>
              {downloading ? "Downloading…" : "Download .docx"}
            </button>
            <button ref={closeRef} className="btn btn-ghost btn-sm" onClick={onClose}>Close</button>
          </div>
        </header>

        <div className="rp-body">
          {error && <p className="cc-error" role="alert">{error}</p>}
          {!data && !error && <p className="hint">Loading preview…</p>}
          {data && (
            <>
              {data.rationale && (
                <div className="brief rp-why"><strong>What we changed:</strong> {data.rationale}</div>
              )}
              <article className="rp-paper" aria-label="Resume preview">
                {data.blocks.map((b, i) => <Block key={i} block={b} />)}
              </article>
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
