import { CareerCoachVisual } from "@/lib/api";

// Draws a diagram the Career Coach produced while teaching. The coach
// supplies structured data only; everything here is plain React text
// nodes (so any markup in a label is shown inertly, never executed) and
// theme-variable CSS. Three shapes: flow (ordered steps), compare (table),
// map (center idea with branches).

const box: React.CSSProperties = {
  border: "1px solid var(--border)", borderRadius: 8, padding: "6px 10px", background: "var(--paper)",
};

export default function VisualDiagram({ visual }: { visual: CareerCoachVisual }) {
  const title = visual.title || "Diagram";
  return (
    <figure aria-label={title} style={{ margin: "10px 0 4px", padding: 10, border: "1px solid var(--border)", borderRadius: 10 }}>
      {visual.title && <figcaption style={{ fontWeight: 600, marginBottom: 8 }}>{visual.title}</figcaption>}

      {visual.kind === "flow" && (
        <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", alignItems: "stretch" }}>
          {visual.steps.map((s, i) => (
            <li key={i} style={{ display: "flex", flexDirection: "column", alignItems: "stretch" }}>
              <div style={{ ...box, display: "flex", gap: 10, alignItems: "baseline" }}>
                <span className="ticket" style={{ minWidth: 24, textAlign: "center" }}>{i + 1}</span>
                <span>
                  <strong>{s.label}</strong>
                  {s.detail && <span className="hint" style={{ display: "block" }}>{s.detail}</span>}
                </span>
              </div>
              {i < visual.steps.length - 1 && (
                <div aria-hidden style={{ textAlign: "center", lineHeight: 1.1, color: "var(--muted, #888)" }}>↓</div>
              )}
            </li>
          ))}
        </ol>
      )}

      {visual.kind === "compare" && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 14 }}>
            <thead>
              <tr>
                <th style={{ ...box, textAlign: "left" }} />
                {visual.columns.map((c, i) => <th key={i} style={{ ...box, textAlign: "left" }}>{c}</th>)}
              </tr>
            </thead>
            <tbody>
              {visual.rows.map((r, i) => (
                <tr key={i}>
                  <th scope="row" style={{ ...box, textAlign: "left" }}>{r.label}</th>
                  {visual.columns.map((_, j) => <td key={j} style={box}>{r.cells[j] ?? ""}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {visual.kind === "map" && (
        <div>
          <div style={{ ...box, textAlign: "center", fontWeight: 700, marginBottom: 8, borderColor: "var(--accent)", background: "var(--accent-soft)" }}>
            {visual.center}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8 }}>
            {visual.branches.map((b, i) => (
              <div key={i} style={box}>
                <div style={{ fontWeight: 600 }}>{b.label}</div>
                <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                  {b.items.map((it, j) => <li key={j}>{it}</li>)}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}
    </figure>
  );
}
