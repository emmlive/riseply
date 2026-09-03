// Custom branding (white-labeling) support for orgs on Riseply
// Enterprise -- derives --accent-hover (darker) and --accent-soft
// (a pale tint) from a single admin-chosen base hex color, the same
// relationship the app's own default --accent/--accent-hover/
// --accent-soft already have to each other (see globals.css). Keeps
// the admin settings UI to one color picker instead of three
// coordinated ones.

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace("#", "");
  return [
    parseInt(clean.substring(0, 2), 16),
    parseInt(clean.substring(2, 4), 16),
    parseInt(clean.substring(4, 6), 16),
  ];
}

function rgbToHex(r: number, g: number, b: number): string {
  const clamp = (n: number) => Math.max(0, Math.min(255, Math.round(n)));
  return "#" + [r, g, b].map((n) => clamp(n).toString(16).padStart(2, "0")).join("");
}

function darken(hex: string, amount: number): string {
  const [r, g, b] = hexToRgb(hex);
  return rgbToHex(r * (1 - amount), g * (1 - amount), b * (1 - amount));
}

function lighten(hex: string, amount: number): string {
  const [r, g, b] = hexToRgb(hex);
  return rgbToHex(r + (255 - r) * amount, g + (255 - g) * amount, b + (255 - b) * amount);
}

export function deriveOrgTheme(accentColor: string): { accent: string; accentHover: string; accentSoft: string } | null {
  if (!/^#[0-9a-fA-F]{6}$/.test(accentColor)) return null;
  return {
    accent: accentColor,
    accentHover: darken(accentColor, 0.18),
    accentSoft: lighten(accentColor, 0.85),
  };
}
