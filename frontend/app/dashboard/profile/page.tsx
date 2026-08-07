"use client";

import { useEffect, useState } from "react";
import { api, User } from "@/lib/api";
import { buildAutoFillBookmarklet } from "@/lib/bookmarklet";

export default function ProfilePage() {
  const [user, setUser] = useState<User | null>(null);
  const [form, setForm] = useState({
    full_name: "", phone: "", location: "", linkedin_url: "",
    portfolio_url: "", notify_email: "", auto_submit: false,
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  async function copyBookmarklet() {
    const link = buildAutoFillBookmarklet({
      full_name: form.full_name, email: user?.email || "", phone: form.phone,
      location: form.location, linkedin_url: form.linkedin_url, portfolio_url: form.portfolio_url,
    });
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    } catch {
      // Clipboard API can be blocked (permissions, non-HTTPS context) --
      // fall back to a manual copy so the person isn't left with a
      // silently-failed button and no way to get the link at all.
      prompt("Copy this link:", link);
    }
  }

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

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Auto-fill bookmarklet</h3>
        <p className="hint" style={{ marginTop: -4 }}>
          Runs entirely in your own browser, on the actual job application page you have open —
          fills in your name, email, phone, and links using the info above. You'll still need to
          attach your resume and hit submit yourself; browsers don't let a script do either of
          those, on purpose.
        </p>

        <p style={{ fontWeight: 600, marginBottom: 4 }}>Option 1: copy the link (most reliable)</p>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button className="btn btn-ghost btn-sm" onClick={copyBookmarklet}>
            {copied ? "Copied ✓" : "Copy auto-fill link"}
          </button>
        </div>
        <ol className="hint" style={{ marginTop: 8, paddingLeft: 18 }}>
          <li>Click the button above to copy the link.</li>
          <li>Right-click your browser's bookmarks bar and choose "Add page" (or click the ⭐ in your address bar, then edit it).</li>
          <li>Paste the copied link into the URL field, give it any name (e.g. "Riseply Auto-fill"), and save.</li>
        </ol>

        <p style={{ fontWeight: 600, marginTop: 16, marginBottom: 4 }}>Option 2: drag the button</p>
        <a
          href={buildAutoFillBookmarklet({
            full_name: form.full_name, email: user?.email || "", phone: form.phone,
            location: form.location, linkedin_url: form.linkedin_url, portfolio_url: form.portfolio_url,
          })}
          className="btn btn-ghost btn-sm"
          onClick={(e) => e.preventDefault()}
          draggable
        >
          📋 Riseply Auto-fill
        </a>
        <p className="hint" style={{ marginTop: 8 }}>
          Press and hold, then drag this button up onto your bookmarks bar — this works in most
          browsers, but if nothing shows up there afterward, use Option 1 instead. Clicking it here
          (rather than dragging) won't do anything, since there's no application form on this page.
        </p>

        <p className="hint" style={{ marginTop: 12 }}>
          Once it's saved as a bookmark, use it by going to a real job application page and
          clicking the bookmark from your bookmarks bar — not from here. If you update your
          profile later, repeat whichever option you used, since the link has today's info baked
          into it.
        </p>
      </div>
    </div>
  );
}
