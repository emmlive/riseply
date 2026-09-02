"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, clearToken, getToken, User, Organization, Application } from "@/lib/api";
import QuotaLimitModal from "@/components/QuotaLimitModal";

// Split into two groups: ALWAYS_NAV shows for everyone; JOB_SEARCH_NAV
// is specifically about finding a job somewhere else (external
// discovery, resume tailoring, tracking applications) and gets hidden
// for anyone affiliated with an organization -- an org admin managing
// Buddy/Mentor/Internal Jobs, or an employee who joined via a code, has
// no real use for external job search in that context, and showing it
// anyway just clutters what should read as a focused enterprise admin
// surface. Internal Jobs (admin-managed openings at the SAME company)
// covers the "help someone find their next role" need for this
// audience instead -- see internal-jobs/page.tsx's own comment for why
// that's a genuinely separate system from this one, not a rename of it.
const ALWAYS_NAV = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/job-buddy", label: "Job Buddy" },
  { href: "/dashboard/billing", label: "Billing" },
  { href: "/dashboard/profile", label: "Profile" },
  { href: "/dashboard/knowledge-base", label: "Knowledge Base" },
  { href: "/dashboard/support", label: "Support" },
  { href: "/security", label: "Security & Trust" },
];

const JOB_SEARCH_NAV = [
  { href: "/dashboard/rise-index", label: "Rise Index" },
  { href: "/dashboard/profiles", label: "Search profiles" },
  { href: "/dashboard/resume", label: "Resume" },
  { href: "/dashboard/applications", label: "Applications" },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [hasOrgAdminAccess, setHasOrgAdminAccess] = useState(false);
  const [isOrgEmployee, setIsOrgEmployee] = useState(false);

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
    // Separate from admin access -- a regular employee who joined an
    // org via a code has an Application with organization_id set, but
    // isn't an OrganizationMember and wouldn't show up in /orgs/mine at
    // all. Both groups get the external job-search nav hidden; only
    // hasOrgAdminAccess additionally unlocks the admin-only pages
    // (Org Buddy, Mentor as a Service, Internal Jobs).
    api<Application[]>("/applications").then((apps) => {
      setIsOrgEmployee(apps.some((a) => a.organization_id !== null));
    }).catch(() => {});
  }, [router]);

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  const showJobSearchNav = !hasOrgAdminAccess && !isOrgEmployee;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand" style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <img src="/brand/icon.svg" alt="" width={26} height={26} />
          <span style={{ fontStyle: "italic" }}>Riseply</span>
        </div>
        <Link href="/dashboard" className={`sidebar-link ${pathname === "/dashboard" ? "active" : ""}`}>
          Overview
        </Link>
        {showJobSearchNav && JOB_SEARCH_NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`sidebar-link ${pathname === item.href ? "active" : ""}`}
          >
            {item.label}
          </Link>
        ))}
        {ALWAYS_NAV.filter((item) => item.href !== "/dashboard").map((item) => (
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
        {hasOrgAdminAccess && (
          <Link
            href="/dashboard/internal-jobs"
            className={`sidebar-link ${pathname === "/dashboard/internal-jobs" ? "active" : ""}`}
          >
            Internal Jobs
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
