"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

interface NextAction { key: string; stage?: string; title: string; detail: string; href: string; cta: string }
const STAGE_LABEL: Record<string, string> = { get_ready: "Get ready", find: "Find", apply: "Apply", win: "Win", grow: "Grow" };

// "Do this next": up to four suggestions worked out from what the person
// already has. Shows nothing while loading, on error, or when there is
// nothing to suggest, so it never gets in the way of the page.
export default function NextActions() {
  const [items, setItems] = useState<NextAction[]>([]);
  useEffect(() => { api<NextAction[]>("/progress/next-actions").then(setItems).catch(() => {}); }, []);
  if (!items.length) return null;
  return (
    <div className="card na-card">
      <h3 style={{ margin: "0 0 8px" }}>Do this next</h3>
      <ul className="na-list">
        {items.map((a) => (
          <li key={a.key}>
            <div>
              {a.stage && STAGE_LABEL[a.stage] && <span className="na-stage">{STAGE_LABEL[a.stage]}</span>}
              <strong>{a.title}</strong>
              {a.detail && <p className="hint" style={{ margin: "2px 0 0" }}>{a.detail}</p>}
            </div>
            <Link href={a.href} className="btn btn-ghost btn-sm">{a.cta}</Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
