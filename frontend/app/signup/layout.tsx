import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Sign up — Riseply",
  description: "Create your free Riseply account — AI job matching, resume tailoring, and interview prep.",
  alternates: { canonical: "https://riseply.com/signup" },
};

export default function SignupLayout({ children }: { children: React.ReactNode }) {
  return children;
}
