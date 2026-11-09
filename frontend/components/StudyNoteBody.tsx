"use client";

import { Block, inline, parseNote } from "@/lib/noteFormat";
import "./StudyNoteBody.css";

function Text({ text }: { text: string }) {
  return <>{inline(text).map((x, i) => (x.b ? <strong key={i}>{x.v}</strong> : <span key={i}>{x.v}</span>))}</>;
}

// A study note laid out for reading: sections, bullets, numbered steps, and
// self-check questions with their answers. `skipTitle` hides the "# " title
// when the page already shows it above.
export default function StudyNoteBody({ text, skipTitle = false, collapsed = false }: {
  text: string; skipTitle?: boolean; collapsed?: boolean;
}) {
  const blocks: Block[] = parseNote(text).filter((b) => !(skipTitle && b.t === "h1"));
  return (
    <div className={`snb${collapsed ? " is-collapsed" : ""}`}>
      {blocks.map((b, i) => {
        switch (b.t) {
          case "h1": return <h2 key={i} className="snb-title">{b.text}</h2>;
          case "meta": return <p key={i} className="snb-meta">{b.text}</p>;
          case "h2": return <h4 key={i} className="snb-h2">{b.text}</h4>;
          case "h3": return <h5 key={i} className="snb-h3">{b.text}</h5>;
          case "p": return <p key={i} className="snb-p"><Text text={b.text} /></p>;
          case "ul": return <ul key={i} className="snb-ul">{b.items.map((it, j) => <li key={j}><Text text={it} /></li>)}</ul>;
          case "ol": return (
            <ol key={i} className="snb-ol">
              {b.items.map((it, j) => (
                <li key={j}><Text text={it.text} />{it.answer ? <div className="snb-answer"><span>Answer</span> <Text text={it.answer} /></div> : null}</li>
              ))}
            </ol>
          );
        }
      })}
    </div>
  );
}
