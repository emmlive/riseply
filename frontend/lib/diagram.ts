// A small diagram a person draws in a Career Coach session: zones (large
// outlined areas such as "Internet" or "Internal data"), boxes inside or
// outside them, and arrows between boxes. describeDiagram() turns it into
// plain text so the coach can critique exactly what was drawn.

export interface DItem { id: string; kind: "zone" | "box"; x: number; y: number; w: number; h: number; label: string }
export interface DLink { id: string; from: string; to: string; label: string }

export const CANVAS_W = 720;
export const CANVAS_H = 420;
export const BOX_W = 128;
export const BOX_H = 46;
export const MAX_ITEMS = 40;

const area = (z: DItem) => z.w * z.h;
const name = (i: DItem) => i.label.trim() || (i.kind === "zone" ? "Unnamed zone" : "Unnamed box");

// The smallest zone whose area holds the box's centre, if any.
export function zoneOf(box: DItem, items: DItem[]): DItem | null {
  const cx = box.x + box.w / 2, cy = box.y + box.h / 2;
  const inside = items.filter((z) => z.kind === "zone" && cx >= z.x && cx <= z.x + z.w && cy >= z.y && cy <= z.y + z.h);
  return inside.sort((a, b) => area(a) - area(b))[0] ?? null;
}

export function describeDiagram(items: DItem[], links: DLink[], note = ""): string {
  const zones = items.filter((i) => i.kind === "zone").sort((a, b) => a.x - b.x || a.y - b.y);
  const boxes = items.filter((i) => i.kind === "box");
  const out: string[] = ["Here is the diagram I drew:", ""];
  for (const z of zones) {
    const inZone = boxes.filter((b) => zoneOf(b, items)?.id === z.id).sort((a, b) => a.x - b.x || a.y - b.y);
    out.push(`Zone "${name(z)}": ${inZone.length ? inZone.map(name).join(", ") : "nothing inside it yet"}`);
  }
  const loose = boxes.filter((b) => !zoneOf(b, items)).sort((a, b) => a.x - b.x || a.y - b.y);
  if (loose.length) out.push(zones.length ? `Outside any zone: ${loose.map(name).join(", ")}` : `Boxes: ${loose.map(name).join(", ")}`);
  const byId = new Map(items.map((i) => [i.id, i] as const));
  const lines = links.flatMap((l) => {
    const a = byId.get(l.from), b = byId.get(l.to);
    if (!a || !b) return [];
    const za = zoneOf(a, items), zb = zoneOf(b, items);
    const crosses = (za?.id ?? "") !== (zb?.id ?? "");
    const where = crosses ? `  [crosses from ${za ? `"${name(za)}"` : "outside any zone"} to ${zb ? `"${name(zb)}"` : "outside any zone"}]` : "";
    return [`${name(a)} → ${name(b)}${l.label.trim() ? ` (${l.label.trim()})` : ""}${where}`];
  });
  if (lines.length) out.push("", "Connections:", ...lines.map((l) => `- ${l}`));
  else if (boxes.length > 1) out.push("", "Connections: none drawn.");
  if (note.trim()) out.push("", note.trim());
  return out.join("\n");
}

// Where a line from the centre of `a` toward `b` leaves a's rectangle.
export function edgePoint(a: DItem, b: DItem): { x: number; y: number } {
  const ax = a.x + a.w / 2, ay = a.y + a.h / 2;
  const dx = b.x + b.w / 2 - ax, dy = b.y + b.h / 2 - ay;
  if (dx === 0 && dy === 0) return { x: ax, y: ay };
  const s = Math.min(a.w / 2 / Math.abs(dx || 1e-9), a.h / 2 / Math.abs(dy || 1e-9));
  return { x: ax + dx * s, y: ay + dy * s };
}
