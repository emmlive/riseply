// Shrinks a picture the person attaches (a photo of a drawing, a screenshot) so
// it uploads fast: longest side 1600px, re-encoded as JPEG. Returns base64
// without the data: prefix, plus a preview URL for the thumbnail.
export interface Attached { media_type: string; data: string; preview: string; name: string }

export async function shrinkImage(file: File, maxSide = 1600): Promise<Attached> {
  if (!/^image\//.test(file.type)) throw new Error("That file is not a picture.");
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((ok, bad) => {
      const i = new Image();
      i.onload = () => ok(i);
      i.onerror = () => bad(new Error("Couldn't read that picture."));
      i.src = url;
    });
    const scale = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(img.naturalWidth * scale));
    c.height = Math.max(1, Math.round(img.naturalHeight * scale));
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = "#fff";            // transparent PNGs become white, not black
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.drawImage(img, 0, 0, c.width, c.height);
    const dataUrl = c.toDataURL("image/jpeg", 0.85);
    const data = dataUrl.split(",")[1] || "";
    if (data.length > 2_900_000) throw new Error("That picture is too large. Try a smaller one.");
    return { media_type: "image/jpeg", data, preview: dataUrl, name: file.name };
  } finally {
    URL.revokeObjectURL(url);
  }
}
