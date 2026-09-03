"use client";

import { deriveOrgTheme } from "@/lib/orgTheme";

// Renders nothing visible -- just a <style> tag overriding the three
// accent CSS custom properties for whatever's rendered below it in the
// DOM. Silently renders nothing at all when accentColor is empty or
// invalid, so a page using this never needs its own guard clause.
export default function OrgThemeOverride({ accentColor }: { accentColor: string | null | undefined }) {
  const theme = accentColor ? deriveOrgTheme(accentColor) : null;
  if (!theme) return null;

  return (
    <style>{`
      :root {
        --accent: ${theme.accent};
        --accent-hover: ${theme.accentHover};
        --accent-soft: ${theme.accentSoft};
      }
    `}</style>
  );
}
