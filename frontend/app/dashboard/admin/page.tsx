"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api, User, AdminUser, AdminRevenue, AdminUsage, AdminErrors, AdminSupportMessage,
  AdminOrganization, AdminSystemHealth, AdminFlaggedMessage,
} from "@/lib/api";

type Tab = "overview" | "users" | "organizations" | "health" | "moderation" | "support" | "admins";

const ALL_TABS: { id: Tab; label: string; roles: string[] }[] = [
  { id: "overview", label: "Overview", roles: ["super", "billing", "readonly"] },
  { id: "users", label: "Users", roles: ["super", "support", "readonly"] },
  { id: "organizations", label: "Organizations", roles: ["super", "billing", "readonly"] },
  { id: "health", label: "System health", roles: ["super", "readonly"] },
  { id: "moderation", label: "Moderation", roles: ["super", "support", "readonly"] },
  { id: "support", label: "Support inbox", roles: ["super", "support", "readonly"] },
  { id: "admins", label: "Admins", roles: ["super"] },
];

const ROLE_LABELS: Record<string, string> = {
  super: "Super admin",
  support: "Support admin",
  billing: "Billing admin",
  readonly: "Read-only admin",
};

export default function AdminPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checked, setChecked] = useState(false);
  const [tab, setTab] = useState<Tab>("overview");

  useEffect(() => {
    api<User>("/me").then((u) => {
      setUser(u);
      setChecked(true);
      if (!u.is_admin) router.push("/dashboard");
    }).catch(() => setChecked(true));
  }, [router]);

  if (!checked) return <p className="muted">Loading…</p>;
  if (!user?.is_admin) return null; // redirecting

  const role = user.admin_role || "super";
  const visibleTabs = ALL_TABS.filter((t) => t.roles.includes(role));
  // If the user's current tab isn't visible for their role, land on the first visible one.
  const activeTab = visibleTabs.some((t) => t.id === tab) ? tab : visibleTabs[0]?.id;

  return (
    <div>
      <div className="card-row" style={{ alignItems: "center" }}>
        <h1 style={{ margin: 0 }}>Admin</h1>
        <span className="pill pill-approved">{ROLE_LABELS[role] || role}</span>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 20, marginTop: 16, flexWrap: "wrap" }}>
        {visibleTabs.map((t) => (
          <button
            key={t.id}
            className="btn btn-ghost btn-sm"
            style={activeTab === t.id ? { background: "var(--accent-soft)", color: "var(--accent-hover)", borderColor: "var(--accent)" } : {}}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === "overview" && <OverviewTab />}
      {activeTab === "users" && <UsersTab currentAdminId={user.id} role={role} />}
      {activeTab === "organizations" && <OrganizationsTab />}
      {activeTab === "health" && <SystemHealthTab />}
      {activeTab === "moderation" && <ModerationTab />}
      {activeTab === "support" && <SupportTab role={role} />}
      {activeTab === "admins" && <AdminsTab currentAdminId={user.id} />}
    </div>
  );
}

function OverviewTab() {
  const [revenue, setRevenue] = useState<AdminRevenue | null>(null);
  const [usage, setUsage] = useState<AdminUsage | null>(null);
  const [errors, setErrors] = useState<AdminErrors | null>(null);

  useEffect(() => {
    api<AdminRevenue>("/admin/revenue").then(setRevenue);
    api<AdminUsage>("/admin/usage").then(setUsage);
    api<AdminErrors>("/admin/errors").then(setErrors);
  }, []);

  return (
    <div>
      {revenue && (
        <div className="rise-hero">
          <div className="rise-stat">
            <div className="value">${revenue.mrr_estimate_usd}</div>
            <div className="label">Estimated MRR</div>
          </div>
          <div className="rise-stat">
            <div className="value">{revenue.active_pro_count}</div>
            <div className="label">Active Pro subscribers</div>
          </div>
          <div className="rise-stat">
            <div className="value">{revenue.total_users}</div>
            <div className="label">Total users</div>
          </div>
        </div>
      )}

      {revenue && (
        <div className="card">
          <h3>Signups</h3>
          <p style={{ margin: 0 }}>
            <span className="mono">{revenue.signups_this_week}</span> this week ·{" "}
            <span className="mono">{revenue.signups_this_month}</span> this month ·{" "}
            <span className="mono">{revenue.free_count}</span> on the free plan
          </p>
        </div>
      )}

      {usage && (
        <div className="card">
          <div className="card-row">
            <h3 style={{ margin: 0 }}>Usage & estimated API cost this month</h3>
            <span className="ticket high">
              total <span className="score">${usage.total_estimated_cost_usd}</span>
            </span>
          </div>
          <p className="hint" style={{ marginTop: 4 }}>
            Cost is a rough estimate based on typical prompt sizes, not exact billing.
          </p>
          {Object.entries(usage.by_action).length === 0 ? (
            <p className="muted">No usage recorded yet this month.</p>
          ) : (
            Object.entries(usage.by_action).map(([action, stat]) => (
              <div key={action} className="points-event-row">
                <span>{action.replace("_", " ")}</span>
                <span>
                  <span className="mono">{stat.count}</span> calls ·{" "}
                  <span className="mono">${stat.estimated_cost_usd}</span>
                </span>
              </div>
            ))
          )}
        </div>
      )}

      {errors && (
        <div className="card">
          <div className="card-row">
            <h3 style={{ margin: 0 }}>Failed Claude calls this month</h3>
            <span className={`pill ${errors.total_failures > 0 ? "pill-rejected" : "pill-approved"}`}>
              {errors.total_failures} total
            </span>
          </div>
          {errors.by_action.length === 0 ? (
            <p className="muted" style={{ marginTop: 10 }}>No failures recorded — clean month so far.</p>
          ) : (
            errors.by_action.map((s) => (
              <div key={s.action} className="points-event-row">
                <span>{s.action.replace("_", " ")}</span>
                <span className="mono">{s.count}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function UsersTab({ currentAdminId, role }: { currentAdminId: number; role: string }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [suspendDraftId, setSuspendDraftId] = useState<number | null>(null);
  const [suspendReason, setSuspendReason] = useState("");

  const canAct = role === "super" || role === "support";
  const canRefund = role === "super" || role === "billing";

  async function load() {
    setUsers(await api<AdminUser[]>("/admin/users"));
  }
  useEffect(() => { load(); }, []);

  async function suspend(id: number) {
    setBusyId(id);
    setError("");
    try {
      await api(`/admin/users/${id}/suspend`, { method: "POST", body: JSON.stringify({ reason: suspendReason }) });
      setSuspendDraftId(null);
      setSuspendReason("");
      await load();
    } catch (err: any) {
      setError(err.message || "Couldn't suspend this user.");
    } finally {
      setBusyId(null);
    }
  }

  async function unsuspend(id: number) {
    setBusyId(id);
    setError("");
    try {
      await api(`/admin/users/${id}/unsuspend`, { method: "POST" });
      await load();
    } catch (err: any) {
      setError(err.message || "Couldn't unsuspend this user.");
    } finally {
      setBusyId(null);
    }
  }

  async function refund(id: number) {
    if (!confirm("Refund this user's most recent charge? This can't be undone.")) return;
    setBusyId(id);
    setError("");
    try {
      const result = await api<{ amount_usd: number }>(`/admin/users/${id}/refund`, {
        method: "POST", body: JSON.stringify({ reason: "" }),
      });
      alert(`Refunded $${result.amount_usd}.`);
    } catch (err: any) {
      setError(err.message || "Couldn't refund this user.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="card">
      {error && <p className="error-text">{error}</p>}
      {users.map((u) => (
        <div key={u.id} className="points-event-row" style={{ alignItems: "flex-start", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", width: "100%", alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 600 }}>
                {u.full_name || "(no name)"} — {u.email}
                {u.id === currentAdminId && <span className="hint"> (you)</span>}
              </div>
              <div className="hint">
                Joined {new Date(u.created_at).toLocaleDateString()} ·{" "}
                {u.rise_points} points · {u.current_streak}-day streak
                {u.is_admin && ` · ${u.admin_role || "admin"}`}
              </div>
              {u.is_suspended && (
                <div className="hint" style={{ color: "var(--danger)" }}>
                  Suspended{u.suspended_reason ? `: ${u.suspended_reason}` : ""}
                </div>
              )}
            </div>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <span className={`pill ${u.subscription_tier === "pro" ? "pill-approved" : "pill-default"}`}>
                {u.subscription_tier}
              </span>
              {u.is_suspended ? (
                <span className="pill pill-rejected">suspended</span>
              ) : null}
            </div>
          </div>

          {u.id !== currentAdminId && !u.is_admin && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {canAct && !u.is_suspended && suspendDraftId !== u.id && (
                <button className="btn btn-danger-ghost btn-sm" onClick={() => setSuspendDraftId(u.id)}>
                  Suspend
                </button>
              )}
              {canAct && u.is_suspended && (
                <button className="btn btn-ghost btn-sm" disabled={busyId === u.id} onClick={() => unsuspend(u.id)}>
                  {busyId === u.id ? "Unsuspending…" : "Unsuspend"}
                </button>
              )}
              {canRefund && u.subscription_tier === "pro" && (
                <button className="btn btn-ghost btn-sm" disabled={busyId === u.id} onClick={() => refund(u.id)}>
                  {busyId === u.id ? "Refunding…" : "Refund latest charge"}
                </button>
              )}
            </div>
          )}

          {suspendDraftId === u.id && (
            <div style={{ display: "flex", gap: 8, width: "100%" }}>
              <input
                type="text"
                placeholder="Reason (shown to the user)"
                value={suspendReason}
                onChange={(e) => setSuspendReason(e.target.value)}
                style={{ flex: 1 }}
              />
              <button className="btn btn-danger-ghost btn-sm" disabled={busyId === u.id} onClick={() => suspend(u.id)}>
                {busyId === u.id ? "Suspending…" : "Confirm"}
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => { setSuspendDraftId(null); setSuspendReason(""); }}>
                Cancel
              </button>
            </div>
          )}
        </div>
      ))}
      {users.length === 0 && <p className="muted">No users yet.</p>}
    </div>
  );
}

function AdminsTab({ currentAdminId }: { currentAdminId: number }) {
  const [admins, setAdmins] = useState<AdminUser[]>([]);
  const [allUsers, setAllUsers] = useState<AdminUser[]>([]);
  const [grantEmail, setGrantEmail] = useState("");
  const [grantRole, setGrantRole] = useState("support");
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  async function load() {
    const [a, u] = await Promise.all([
      api<AdminUser[]>("/admin/admins"),
      api<AdminUser[]>("/admin/users?limit=200"),
    ]);
    setAdmins(a);
    setAllUsers(u);
  }
  useEffect(() => { load(); }, []);

  async function changeRole(id: number, role: string) {
    setBusyId(id);
    setError("");
    try {
      await api(`/admin/users/${id}/set-admin-role`, { method: "POST", body: JSON.stringify({ role }) });
      await load();
    } catch (err: any) {
      setError(err.message || "Couldn't update this admin's role.");
    } finally {
      setBusyId(null);
    }
  }

  async function revoke(id: number) {
    if (!confirm("Remove admin access for this account?")) return;
    await changeRole(id, "");
  }

  async function grant() {
    const target = allUsers.find((u) => u.email.toLowerCase() === grantEmail.trim().toLowerCase());
    if (!target) {
      setError("No user with that email — check the Users tab for the exact address.");
      return;
    }
    await changeRole(target.id, grantRole);
    setGrantEmail("");
  }

  return (
    <div>
      <div className="card">
        <h3>Grant admin access</h3>
        <p className="hint">Enter the email of an existing Riseply account.</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
          <input
            type="email"
            placeholder="person@company.com"
            value={grantEmail}
            onChange={(e) => setGrantEmail(e.target.value)}
            style={{ flex: 1, minWidth: 200 }}
          />
          <select value={grantRole} onChange={(e) => setGrantRole(e.target.value)}>
            <option value="super">Super admin</option>
            <option value="support">Support admin</option>
            <option value="billing">Billing admin</option>
            <option value="readonly">Read-only admin</option>
          </select>
          <button className="btn btn-primary btn-sm" onClick={grant} disabled={!grantEmail.trim()}>
            Grant
          </button>
        </div>
        {error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
      </div>

      <div className="card">
        <h3>Current admins</h3>
        {admins.map((a) => (
          <div key={a.id} className="points-event-row" style={{ alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 600 }}>
                {a.full_name || "(no name)"} — {a.email}
                {a.id === currentAdminId && <span className="hint"> (you)</span>}
              </div>
              <div className="hint">{ROLE_LABELS[a.admin_role] || a.admin_role || "super"}</div>
            </div>
            {a.id !== currentAdminId && (
              <div style={{ display: "flex", gap: 6 }}>
                <select
                  value={a.admin_role || "super"}
                  disabled={busyId === a.id}
                  onChange={(e) => changeRole(a.id, e.target.value)}
                >
                  <option value="super">Super admin</option>
                  <option value="support">Support admin</option>
                  <option value="billing">Billing admin</option>
                  <option value="readonly">Read-only admin</option>
                </select>
                <button className="btn btn-danger-ghost btn-sm" disabled={busyId === a.id} onClick={() => revoke(a.id)}>
                  Revoke
                </button>
              </div>
            )}
          </div>
        ))}
        {admins.length === 0 && <p className="muted">No admins found.</p>}
      </div>
    </div>
  );
}

function OrganizationsTab() {
  const [orgs, setOrgs] = useState<AdminOrganization[]>([]);

  useEffect(() => { api<AdminOrganization[]>("/admin/organizations").then(setOrgs); }, []);

  const totalMrr = orgs.reduce((sum, o) => sum + o.estimated_mrr_usd, 0);

  return (
    <div>
      <div className="rise-hero">
        <div className="rise-stat">
          <div className="value">${totalMrr.toFixed(2)}</div>
          <div className="label">Estimated org MRR</div>
        </div>
        <div className="rise-stat">
          <div className="value">{orgs.length}</div>
          <div className="label">Organizations</div>
        </div>
        <div className="rise-stat">
          <div className="value">{orgs.reduce((sum, o) => sum + o.member_count, 0)}</div>
          <div className="label">Total members</div>
        </div>
      </div>

      <div className="card">
        {orgs.map((org) => (
          <div key={org.id} className="points-event-row" style={{ alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 600 }}>{org.name}</div>
              <div className="hint">
                {org.member_count} member{org.member_count === 1 ? "" : "s"} of {org.included_seats} included
                {org.overage_seats > 0 && ` (+${org.overage_seats} overage)`} ·{" "}
                Joined {new Date(org.created_at).toLocaleDateString()}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div className="mono">${org.estimated_mrr_usd}/mo</div>
              <span className={`pill ${org.subscription_status === "active" ? "pill-approved" : "pill-default"}`}>
                {org.plan} · {org.subscription_status || "inactive"}
              </span>
            </div>
          </div>
        ))}
        {orgs.length === 0 && <p className="muted">No organizations yet.</p>}
      </div>
    </div>
  );
}

function SystemHealthTab() {
  const [health, setHealth] = useState<AdminSystemHealth | null>(null);

  useEffect(() => { api<AdminSystemHealth>("/admin/system-health").then(setHealth); }, []);

  if (!health) return <p className="muted">Loading…</p>;

  const statusPill: Record<string, string> = {
    healthy: "pill-approved",
    stale: "pill-pending",
    silent: "pill-rejected",
  };

  return (
    <div>
      <div className="card">
        <h3>Job discovery sources</h3>
        <p className="hint">{health.total_jobs_in_pool} jobs total in the shared pool.</p>
        {health.job_sources.map((s) => (
          <div key={s.source} className="points-event-row" style={{ alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 600 }}>{s.source}</div>
              <div className="hint">
                {s.jobs_last_24h} new in 24h · {s.jobs_last_7d} in 7d
                {s.last_discovered_at && ` · last seen ${new Date(s.last_discovered_at).toLocaleString()}`}
                {!s.last_discovered_at && " · never discovered anything"}
              </div>
            </div>
            <span className={`pill ${statusPill[s.status] || "pill-default"}`}>{s.status}</span>
          </div>
        ))}
        {health.job_sources.length === 0 && <p className="muted">No sources configured.</p>}
      </div>
    </div>
  );
}

function ModerationTab() {
  const [messages, setMessages] = useState<AdminFlaggedMessage[]>([]);
  const [filter, setFilter] = useState<"unresolved" | "resolved" | "all">("unresolved");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState("");

  async function load(f: typeof filter) {
    const qs = f === "unresolved" ? "?resolved=false" : f === "resolved" ? "?resolved=true" : "";
    setMessages(await api<AdminFlaggedMessage[]>(`/admin/flagged-messages${qs}`));
  }
  useEffect(() => { load(filter); }, [filter]);

  async function resolve(id: number) {
    setBusyId(id);
    setError("");
    try {
      await api(`/admin/flagged-messages/${id}/resolve`, { method: "POST" });
      await load(filter);
    } catch (err: any) {
      setError(err.message || "Couldn't mark this resolved.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <p className="hint" style={{ marginBottom: 12 }}>
        Flagged by a keyword scan on Job Buddy messages — self-harm, harassment/discrimination,
        or workplace-safety language. This is a coarse signal for review, not a moderation action.
      </p>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {(["unresolved", "resolved", "all"] as const).map((f) => (
          <button
            key={f}
            className="btn btn-ghost btn-sm"
            style={filter === f ? { background: "var(--accent-soft)", color: "var(--accent-hover)", borderColor: "var(--accent)" } : {}}
            onClick={() => setFilter(f)}
          >
            {f === "unresolved" ? "Needs review" : f === "resolved" ? "Resolved" : "All"}
          </button>
        ))}
      </div>

      {error && <p className="error-text">{error}</p>}
      {messages.length === 0 && <div className="empty-state">Nothing here.</div>}

      {messages.map((m) => (
        <div key={m.id} className="card">
          <div className="card-row">
            <div>
              <h3 style={{ margin: 0 }}>{m.user_email} · {m.role}</h3>
              <p className="hint" style={{ margin: "2px 0" }}>
                {m.flag_reason} · {new Date(m.created_at).toLocaleString()}
              </p>
            </div>
            <span className={`pill ${m.flag_resolved_at ? "pill-approved" : "pill-pending"}`}>
              {m.flag_resolved_at ? "resolved" : "needs review"}
            </span>
          </div>
          <p style={{ margin: "10px 0" }}>{m.content}</p>
          {!m.flag_resolved_at && (
            <button className="btn btn-ghost btn-sm" disabled={busyId === m.id} onClick={() => resolve(m.id)}>
              {busyId === m.id ? "Marking…" : "Mark resolved"}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function SupportTab({ role }: { role: string }) {
  const [messages, setMessages] = useState<AdminSupportMessage[]>([]);
  const [filter, setFilter] = useState<"" | "open" | "resolved">("open");
  const [replyDrafts, setReplyDrafts] = useState<Record<number, string>>({});
  const [sendingId, setSendingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const canReply = role === "super" || role === "support";

  async function load(status: string) {
    const qs = status ? `?status=${status}` : "";
    setMessages(await api<AdminSupportMessage[]>(`/admin/support-messages${qs}`));
  }

  useEffect(() => { load(filter); }, [filter]);

  async function sendReply(id: number) {
    const reply = replyDrafts[id];
    if (!reply?.trim()) return;
    setSendingId(id);
    setError("");
    try {
      await api(`/admin/support-messages/${id}/reply`, { method: "POST", body: JSON.stringify({ reply }) });
      await load(filter);
    } catch (err: any) {
      setError(err.message || "Couldn't send the reply.");
    } finally {
      setSendingId(null);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {(["open", "resolved", ""] as const).map((f) => (
          <button
            key={f || "all"}
            className="btn btn-ghost btn-sm"
            style={filter === f ? { background: "var(--accent-soft)", color: "var(--accent-hover)", borderColor: "var(--accent)" } : {}}
            onClick={() => setFilter(f)}
          >
            {f === "" ? "All" : f === "open" ? "Open" : "Resolved"}
          </button>
        ))}
      </div>

      {error && <p className="error-text">{error}</p>}

      {messages.length === 0 && <div className="empty-state">Nothing here.</div>}

      {messages.map((m) => (
        <div key={m.id} className="card">
          <div className="card-row">
            <div>
              <h3 style={{ margin: 0 }}>{m.subject}</h3>
              <p className="hint" style={{ margin: "2px 0" }}>
                {m.user_email} · {new Date(m.created_at).toLocaleString()}
              </p>
            </div>
            <span className={`pill ${m.status === "open" ? "pill-pending" : "pill-approved"}`}>{m.status}</span>
          </div>
          <p style={{ margin: "10px 0" }}>{m.message}</p>

          {m.admin_reply ? (
            <div className="brief">Replied: {m.admin_reply}</div>
          ) : canReply ? (
            <div style={{ marginTop: 10 }}>
              <textarea
                rows={3}
                placeholder="Write a reply…"
                value={replyDrafts[m.id] || ""}
                onChange={(e) => setReplyDrafts({ ...replyDrafts, [m.id]: e.target.value })}
              />
              <button
                className="btn btn-primary btn-sm"
                style={{ marginTop: 8 }}
                disabled={sendingId === m.id || !(replyDrafts[m.id] || "").trim()}
                onClick={() => sendReply(m.id)}
              >
                {sendingId === m.id ? "Sending…" : "Send reply"}
              </button>
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}
