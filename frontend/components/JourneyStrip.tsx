"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

interface Stage { key: string; label: string; blurb: string; stat: string; href: string; state: "done" | "current" | "todo" }
interface Journey { current: string; stages: Stage[] }

// The five stages Riseply is organised around, with the person's place on them.
// Shows nothing while loading or on error, so it never gets in the way.
export default function JourneyStrip() {
  const [j, setJ] = useState<Journey | null>(null);
  useEffect(() => { api<Journey>("/progress/journey").then(setJ).catch(() => {}); }, []);
  if (!j) return null;
  return (
    <nav className="journey" aria-label="Your career loop">
      {j.stages.map((s, i) => (
        <Link key={s.key} href={s.href} className={`journey-step ${s.state}`} aria-current={s.state === "current" ? "step" : undefined}>
          <span className="journey-mark" aria-hidden="true">{s.state === "done" ? "\u2713" : i + 1}</span>
          <span className="journey-text">
            <strong>{s.label}</strong>
            <span className="journey-stat">{s.stat}</span>
          </span>
        </Link>
      ))}
    </nav>
  );
}
