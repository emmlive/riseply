"use client";

import { useEffect, useState } from "react";
import { applyTheme, getThemePref, setThemePref, ThemePref } from "@/lib/theme";

const OPTIONS: { value: ThemePref; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "Auto" },
];

// Light, Dark, or Auto (follow the device). Auto keeps following the device
// if its setting changes while the page is open.
export default function ThemeToggle() {
  const [pref, setPref] = useState<ThemePref>("system");

  useEffect(() => {
    setPref(getThemePref());
  }, []);

  useEffect(() => {
    if (pref !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => applyTheme("system");
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [pref]);

  function pick(v: ThemePref) {
    setPref(v);
    setThemePref(v);
  }

  return (
    <div className="theme-toggle" role="group" aria-label="Theme">
      {OPTIONS.map((o) => (
        <button key={o.value} type="button" className={pref === o.value ? "on" : ""} aria-pressed={pref === o.value} onClick={() => pick(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
