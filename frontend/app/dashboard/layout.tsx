"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, clearToken, getToken, User, Organization } from "@/lib/api";
import QuotaLimitModal from "@/components/QuotaLimitModal";

const NAV = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/rise-index", label: "Rise Index" },
  { href: "/dashboard/profiles", label: "Search profiles" },
  { href: "/dashboard/resume", label: "Resume" },
  { href: "/dashboard/applications", label: "Applications" },
  { href: "/dashboard/job-buddy", label: "Job Buddy" },
  { href: "/dashboard/billing", label: "Billing" },
  { href: "/dashboard/profile", label: "Profile" },
  { href: "/dashboard/knowledge-base", label: "Knowledge Base" },
  { href: "/dashboard/support", label: "Support" },
  { href: "/security", label: "Security & Trust" },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [hasOrgAdminAccess, setHasOrgAdminAccess] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api<User>("/me").then(setUser).catch(() => {});
    // "Org Buddy" only makes sense for someone who actually administers
    // an org (fully, or as a department admin) -- a plain individual
    // user, or an employee who just joined via a code, would otherwise
    // hit a confusing "create an organization" prompt that doesn't
    // apply to them. Everything relevant to a plain employee is already
    // surfaced through Job Buddy.
    api<Organization[]>("/orgs/mine").then((orgs) => setHasOrgAdminAccess(orgs.length > 0)).catch(() => {});
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
        {hasOrgAdminAccess && (
          <Link
            href="/dashboard/org-buddy"
            className={`sidebar-link ${pathname === "/dashboard/org-buddy" ? "active" : ""}`}
          >
            Org Buddy
          </Link>
        )}
        {hasOrgAdminAccess && (
          <Link
            href="/dashboard/mentor-as-a-service"
            className={`sidebar-link ${pathname === "/dashboard/mentor-as-a-service" ? "active" : ""}`}
          >
            Mentor as a Service
          </Link>
        )}
        {user?.is_admin && (
          <Link
            href="/dashboard/admin"
            className={`sidebar-link ${pathname === "/dashboard/admin" ? "active" : ""}`}
            style={{ color: "var(--danger)", fontWeight: 600 }}
          >
            Admin
          </Link>
        )}
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
      <QuotaLimitModal />
    </div>
  );
}
