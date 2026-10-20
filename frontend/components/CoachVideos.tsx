"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import MediaEmbed from "@/components/MediaEmbed";

interface Video { id: string; title: string; channel: string; thumb: string }
interface Result { query: string; videos: Video[]; search_url: string; note: string }

// "Watch a video on this": real YouTube videos found by search for what the
// coach is teaching. Opened on request, so nothing loads (or counts against an
// allowance) until the person asks. Always offers the YouTube search link, so
// it still helps when the in-app videos are off or used up.
export default function CoachVideos({ topic }: { topic: string }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState(topic);
  const [res, setRes] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [playing, setPlaying] = useState(0);

  async function find() {
    if (busy || q.trim().length < 2) return;
    setBusy(true); setError(""); setPlaying(0);
    try {
      setRes(await api<Result>(`/career-coach/videos?q=${encodeURIComponent(q.trim())}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't look for videos. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div className="cc-video-bar">
        <button className="btn btn-ghost btn-sm" onClick={() => { setOpen(true); find(); }}>
          🎬 Watch a video on this
        </button>
      </div>
    );
  }
  const current = res?.videos[playing];
  return (
    <div className="cc-video">
      <div className="cc-video-head">
        <strong>Videos</strong>
        <button className="sg-link" onClick={() => setOpen(false)}>Hide</button>
      </div>
      <div className="cc-video-search">
        <input aria-label="What to find a video about" value={q} maxLength={100}
               onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") find(); }} />
        <button className="btn btn-ghost btn-sm" onClick={find} disabled={busy || q.trim().length < 2}>
          {busy ? "Looking…" : "Find videos"}
        </button>
      </div>
      {error && <p className="cc-error" role="alert">{error}</p>}
      {current && <MediaEmbed url={`https://www.youtube.com/watch?v=${current.id}`} />}
      {res && res.videos.length > 0 && (
        <ul className="cc-video-list">
          {res.videos.map((v, i) => (
            <li key={v.id}>
              <button className={i === playing ? "is-on" : ""} onClick={() => setPlaying(i)} aria-pressed={i === playing}>
                {v.thumb && /* eslint-disable-next-line @next/next/no-img-element */ <img src={v.thumb} alt="" width={96} height={54} loading="lazy" />}
                <span><strong>{v.title}</strong>{v.channel && <span className="muted"> · {v.channel}</span>}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {res?.note && <p className="hint" style={{ margin: "6px 0" }}>{res.note}</p>}
      {res && (
        <p className="hint" style={{ margin: "6px 0 0" }}>
          <a href={res.search_url} target="_blank" rel="noopener noreferrer">Search YouTube for more</a>.
          {" "}Videos come from YouTube search and aren&apos;t reviewed by Riseply, so check anything important with the coach.
        </p>
      )}
    </div>
  );
}
