/**
 * Renders an admin-supplied media_url safely.
 *
 * Security design (mirrors the backend's _validate_media_url in
 * routers/org_buddy.py, which already rejects non-http(s) schemes
 * server-side -- this is a second, independent layer, not a
 * substitute for that):
 *
 * - Only a small allowlist of known video providers (YouTube, Vimeo,
 *   Loom) ever get a real <iframe> embed. The embed URL is BUILT from
 *   a regex-extracted video ID, never used verbatim from user input --
 *   an admin can't smuggle an arbitrary iframe src by disguising it as
 *   a "YouTube link".
 * - Recognized image extensions render as a plain <img> -- except
 *   .svg, deliberately excluded (SVGs have a messier script-execution
 *   history than raster formats).
 * - Everything else (Drive/Dropbox/Notion links, PDFs, anything
 *   unrecognized) renders as a plain link, never auto-embedded, always
 *   with rel="noopener noreferrer" to prevent tabnabbing.
 * - Never fetched or proxied by Riseply's own servers -- the browser
 *   loads it directly. No SSRF surface on our side.
 */

function extractYouTubeId(url: string): string | null {
  const m = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{6,15})/);
  return m ? m[1] : null;
}

function extractVimeoId(url: string): string | null {
  const m = url.match(/vimeo\.com\/(?:video\/)?(\d+)/);
  return m ? m[1] : null;
}

function extractLoomId(url: string): string | null {
  const m = url.match(/loom\.com\/share\/([a-zA-Z0-9]+)/);
  return m ? m[1] : null;
}

const IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".webp"]; // deliberately excludes .svg

function isImageUrl(url: string): boolean {
  try {
    const path = new URL(url).pathname.toLowerCase();
    return IMAGE_EXTENSIONS.some((ext) => path.endsWith(ext));
  } catch {
    return false;
  }
}

export default function MediaEmbed({ url }: { url: string }) {
  if (!url) return null;

  const youtubeId = extractYouTubeId(url);
  if (youtubeId) {
    return (
      <div style={{ position: "relative", paddingBottom: "56.25%", height: 0, margin: "10px 0", borderRadius: 8, overflow: "hidden" }}>
        <iframe
          src={`https://www.youtube.com/embed/${youtubeId}`}
          style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", border: 0 }}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          loading="lazy"
          referrerPolicy="strict-origin-when-cross-origin"
          sandbox="allow-scripts allow-same-origin allow-presentation"
          title="Video"
        />
      </div>
    );
  }

  const vimeoId = extractVimeoId(url);
  if (vimeoId) {
    return (
      <div style={{ position: "relative", paddingBottom: "56.25%", height: 0, margin: "10px 0", borderRadius: 8, overflow: "hidden" }}>
        <iframe
          src={`https://player.vimeo.com/video/${vimeoId}`}
          style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", border: 0 }}
          allow="autoplay; fullscreen; picture-in-picture"
          allowFullScreen
          loading="lazy"
          referrerPolicy="strict-origin-when-cross-origin"
          sandbox="allow-scripts allow-same-origin allow-presentation"
          title="Video"
        />
      </div>
    );
  }

  const loomId = extractLoomId(url);
  if (loomId) {
    return (
      <div style={{ position: "relative", paddingBottom: "56.25%", height: 0, margin: "10px 0", borderRadius: 8, overflow: "hidden" }}>
        <iframe
          src={`https://www.loom.com/embed/${loomId}`}
          style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", border: 0 }}
          allow="autoplay; fullscreen"
          allowFullScreen
          loading="lazy"
          referrerPolicy="strict-origin-when-cross-origin"
          sandbox="allow-scripts allow-same-origin allow-presentation"
          title="Video"
        />
      </div>
    );
  }

  if (isImageUrl(url)) {
    return (
      <img
        src={url}
        alt=""
        style={{ maxWidth: "100%", borderRadius: 8, margin: "10px 0", display: "block" }}
        loading="lazy"
        onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
      />
    );
  }

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="btn btn-ghost btn-sm"
      style={{ display: "inline-block", margin: "10px 0" }}
    >
      View attachment ↗
    </a>
  );
}
