"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api, User, AdminUser, AdminRevenue, AdminUsage, AdminErrors, AdminSupportMessage,
} from "@/lib/api";

type Tab = "overview" | "users" | "support";

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

  return (
    <div>
      <h1>Admin</h1>

      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        {(["overview", "users", "support"] as Tab[]).map((t) => (
          <button
            key={t}
            className="btn btn-ghost btn-sm"
            style={tab === t ? { background: "var(--accent-soft)", color: "var(--accent-hover)", borderColor: "var(--accent)" } : {}}
            onClick={() => setTab(t)}
          >
            {t === "overview" ? "Overview" : t === "users" ? "Users" : "Support inbox"}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab />}
      {tab === "users" && <UsersTab />}
      {tab === "support" && <SupportTab />}
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

function UsersTab() {
  const [users, setUsers] = useState<AdminUser[]>([]);

  useEffect(() => {
    api<AdminUser[]>("/admin/users").then(setUsers);
  }, []);

  return (
    <div className="card">
      {users.map((u) => (
        <div key={u.id} className="points-event-row" style={{ alignItems: "center" }}>
          <div>
            <div style={{ fontWeight: 600 }}>{u.full_name || "(no name)"} — {u.email}</div>
            <div className="hint">
              Joined {new Date(u.created_at).toLocaleDateString()} ·{" "}
              {u.rise_points} points · {u.current_streak}-day streak
              {u.is_admin && " · admin"}
            </div>
          </div>
          <span className={`pill ${u.subscription_tier === "pro" ? "pill-approved" : "pill-default"}`}>
            {u.subscription_tier}
          </span>
        </div>
      ))}
      {users.length === 0 && <p className="muted">No users yet.</p>}
    </div>
  );
}

function SupportTab() {
  const [messages, setMessages] = useState<AdminSupportMessage[]>([]);
  const [filter, setFilter] = useState<"" | "open" | "resolved">("open");
  const [replyDrafts, setReplyDrafts] = useState<Record<number, string>>({});
  const [sendingId, setSendingId] = useState<number | null>(null);
  const [error, setError] = useState("");

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
          ) : (
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
          )}
        </div>
      ))}
    </div>
  );
}
