"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, clearToken, getToken, User, Organization, Application } from "@/lib/api";
import { isPreviewingAsIndividual, setPreviewAsIndividual } from "@/lib/previewMode";
import QuotaLimitModal from "@/components/QuotaLimitModal";

// Split into two groups: ALWAYS_NAV shows for everyone; INDIVIDUAL_NAV
// is specifically about an individual's OWN job search (external
// discovery, resume tailoring, tracking applications) or paying for
// higher limits on those same features, and gets hidden for anyone
// affiliated with an organization -- an org admin managing Buddy/
// Mentor/Internal Jobs, or an employee who joined via a code, has no
// real use for external job search in that context, and showing it
// anyway just clutters what should read as a focused enterprise admin
// surface. Billing belongs in this group too, not ALWAYS_NAV -- its
// entire purpose is selling higher limits on matching/search-profiles/
// tailoring, so once those are hidden, a page pitching an upgrade for
// invisible features is just confusing, not neutral. Internal Jobs
// (admin-managed openings at the SAME company) covers the "help
// someone find their next role" need for this audience instead -- see
// internal-jobs/page.tsx's own comment for why that's a genuinely
// separate system from external search, not a rename of it.
const ALWAYS_NAV = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/profile", label: "Profile" },
  { href: "/dashboard/knowledge-base", label: "Knowledge Base" },
  { href: "/dashboard/support", label: "Support" },
  { href: "/security", label: "Security & Trust" },
];

const INDIVIDUAL_NAV = [
  { href: "/dashboard/rise-index", label: "Rise Index" },
  { href: "/dashboard/profiles", label: "Search profiles" },
  { href: "/dashboard/resume", label: "Resume" },
  { href: "/dashboard/applications", label: "Applications" },
  { href: "/dashboard/billing", label: "Billing" },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [realHasOrgAdminAccess, setRealHasOrgAdminAccess] = useState(false);
  const [realIsOrgEmployee, setRealIsOrgEmployee] = useState(false);
  const [previewingAsIndividual, setPreviewingAsIndividual] = useState(false);

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
    api<Organization[]>("/orgs/mine").then((orgs) => setRealHasOrgAdminAccess(orgs.length > 0)).catch(() => {});
    // Separate from admin access -- a regular employee who joined an
    // org via a code has an Application with organization_id set, but
    // isn't an OrganizationMember and wouldn't show up in /orgs/mine at
    // all. Both groups get the external job-search nav hidden; only
    // hasOrgAdminAccess additionally unlocks the admin-only pages
    // (Org Buddy, Mentor as a Service, Internal Jobs).
    api<Application[]>("/applications").then((apps) => {
      setRealIsOrgEmployee(apps.some((a) => a.organization_id !== null));
    }).catch(() => {});
    setPreviewingAsIndividual(isPreviewingAsIndividual());
  }, [router]);

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  function togglePreview() {
    const next = !previewingAsIndividual;
    setPreviewAsIndividual(next);
    // A hard reload, not router.push/refresh -- this page and Overview
    // both read the flag fresh on mount, and a soft navigation to a
    // route you're already on isn't guaranteed to actually remount
    // everything that depends on it. A full reload is a small, one-time
    // cost for a staff QA toggle, and it's the version that's
    // guaranteed correct.
    window.location.href = "/dashboard";
  }

  // Super-admin-only display override -- see previewMode.ts's own
  // comment for why this is a client-side-only preview, never a real
  // change to the account's actual org affiliation. Every other user
  // (including a plain org admin or employee) always sees their real
  // hasOrgAdminAccess/isOrgEmployee values, no exceptions.
  const isPreviewActive = !!user?.is_admin && previewingAsIndividual;
  const hasOrgAdminAccess = isPreviewActive ? false : realHasOrgAdminAccess;
  const isOrgEmployee = isPreviewActive ? false : realIsOrgEmployee;

  const showIndividualNav = !hasOrgAdminAccess && !isOrgEmployee;

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
        {/* Job Buddy is an employee's own home base (mentor, meetings,
            internal jobs, onboarding chat) -- tied to THEIR OWN
            org-linked Application. A pure admin with no employee
            Application of their own would land on an empty picker
            offering to "add a job you already have," which isn't
            meaningfully different from not having the link at all.
            Shown whenever isOrgEmployee is true regardless of admin
            status (someone can genuinely be both, e.g. an admin who
            also joined their own org as an employee to preview the
            experience -- in that case Job Buddy has real content and
            should stay), and also shown to plain individual users who
            are neither admin nor org employee (their normal, unrelated
            use of Job Buddy for personal job tracking). */}
        {(isOrgEmployee || (!hasOrgAdminAccess && !isOrgEmployee)) && (
          <Link href="/dashboard/job-buddy" className={`sidebar-link ${pathname === "/dashboard/job-buddy" ? "active" : ""}`}>
            Job Buddy
          </Link>
        )}
        {showIndividualNav && INDIVIDUAL_NAV.map((item) => (
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
        {user?.is_admin && (
          <button
            onClick={togglePreview}
            className="sidebar-link"
            style={{ textAlign: "left", background: previewingAsIndividual ? "var(--accent-soft)" : "transparent", border: "none", cursor: "pointer" }}
          >
            {previewingAsIndividual ? "◀ Exit individual preview" : "Preview as individual"}
          </button>
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
      <main className="main">
        {isPreviewActive && (
          <div style={{
            background: "var(--amber-soft, #FBEEE0)", color: "var(--amber, #C97A2B)",
            padding: "8px 16px", borderRadius: 8, marginBottom: 16, fontSize: "0.85rem",
            display: "flex", justifyContent: "space-between", alignItems: "center",
          }}>
            <span>Previewing as an individual user — your real account and org data are unchanged.</span>
            <button onClick={togglePreview} className="btn btn-ghost btn-sm">Exit preview</button>
          </div>
        )}
        {children}
      </main>
      <QuotaLimitModal />
    </div>
  );
}
