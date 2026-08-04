"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, clearToken, getToken, User } from "@/lib/api";

const NAV = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/rise-index", label: "Rise Index" },
  { href: "/dashboard/profiles", label: "Search profiles" },
  { href: "/dashboard/resume", label: "Resume" },
  { href: "/dashboard/applications", label: "Applications" },
  { href: "/dashboard/job-buddy", label: "Job Buddy" },
  { href: "/dashboard/billing", label: "Billing" },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api<User>("/me").then(setUser).catch(() => {});
  }, [router]);

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand" style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <img src="/brand/icon.svg" alt="" width={26} height={26} />
          <span style={{ fontStyle: "italic" }}>Riseply</span>
        </div>
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`sidebar-link ${pathname === item.href ? "active" : ""}`}
          >
            {item.label}
          </Link>
        ))}
        <div style={{ flex: 1 }} />
        {user && (
          <div style={{ padding: "0 8px", fontSize: "0.82rem" }} className="muted">
            {user.email}
          </div>
        )}
        <button onClick={handleLogout} className="btn btn-ghost btn-sm" style={{ margin: "8px 8px 0" }}>
          Log out
        </button>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
