import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Log in — Riseply",
  description: "Log in to your Riseply account.",
  alternates: { canonical: "https://riseply.com/login" },
};

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return children;
}
