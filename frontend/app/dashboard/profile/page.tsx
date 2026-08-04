"use client";

import { useEffect, useState } from "react";
import { api, User } from "@/lib/api";

export default function ProfilePage() {
  const [user, setUser] = useState<User | null>(null);
  const [form, setForm] = useState({
    full_name: "", phone: "", location: "", linkedin_url: "",
    portfolio_url: "", notify_email: "", auto_submit: false,
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api<User>("/me").then((u) => {
      setUser(u);
      setForm({
        full_name: u.full_name, phone: u.phone, location: u.location,
        linkedin_url: u.linkedin_url, portfolio_url: u.portfolio_url,
        notify_email: u.notify_email, auto_submit: u.auto_submit,
      });
    });
  }, []);

  async function save() {
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      await api("/me", { method: "PATCH", body: JSON.stringify(form) });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err: any) {
      setError(err.message || "Couldn't save your profile.");
    } finally {
      setSaving(false);
    }
  }

  if (!user) return <p className="muted">Loading…</p>;

  return (
    <div>
      <div className="topbar">
        <h1>Profile</h1>
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save changes"}
        </button>
      </div>

      <div className="card">
        <div className="field">
          <label>Email</label>
          <input value={user.email} disabled style={{ opacity: 0.6 }} />
          <p className="hint">Your login email — contact support to change this.</p>
        </div>

        <div className="field">
          <label>Full name</label>
          <input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        </div>

        <div className="field">
          <label>Phone</label>
          <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
        </div>

        <div className="field">
          <label>Location</label>
          <input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })}
                 placeholder="e.g. Chicago, IL" />
        </div>

        <div className="field">
          <label>LinkedIn URL</label>
          <input value={form.linkedin_url} onChange={(e) => setForm({ ...form, linkedin_url: e.target.value })}
                 placeholder="https://linkedin.com/in/you" />
        </div>

        <div className="field">
          <label>Portfolio URL</label>
          <input value={form.portfolio_url} onChange={(e) => setForm({ ...form, portfolio_url: e.target.value })}
                 placeholder="https://yourportfolio.com" />
        </div>

        <div className="field">
          <label>Notification email</label>
          <input value={form.notify_email} onChange={(e) => setForm({ ...form, notify_email: e.target.value })} />
          <p className="hint">Where match alerts and generated documents get sent. Defaults to your login email.</p>
        </div>

        {saved && <p style={{ color: "var(--accent)" }}>Saved.</p>}
        {error && <p className="error-text">{error}</p>}
      </div>
    </div>
  );
}
