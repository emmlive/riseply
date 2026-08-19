"use client";

import { useEffect, useState } from "react";
import { api, User, API_URL } from "@/lib/api";
import { buildAutoFillBookmarklet } from "@/lib/bookmarklet";

export default function ProfilePage() {
  const [user, setUser] = useState<User | null>(null);
  const [form, setForm] = useState({
    full_name: "", phone: "", location: "", linkedin_url: "",
    portfolio_url: "", notify_email: "", auto_submit: false,
    notification_preference: "every_match", notification_min_score: 0,
    notification_channel: "email", sms_consent: false,
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  async function copyBookmarklet() {
    if (!user?.bookmarklet_token) return;
    const link = buildAutoFillBookmarklet(user.bookmarklet_token, API_URL);
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
        notification_preference: u.notification_preference, notification_min_score: u.notification_min_score,
        notification_channel: u.notification_channel, sms_consent: u.sms_consent,
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

        <div className="field">
          <label>New match notifications</label>
          <select value={form.notification_preference}
                  onChange={(e) => setForm({ ...form, notification_preference: e.target.value })}>
            <option value="every_match">Notify me for every match</option>
            <option value="daily_digest">Once-a-day digest instead</option>
            <option value="off">Don't notify me — I'll check the dashboard</option>
          </select>
          <p className="hint">
            {form.notification_preference === "every_match" && "One alert per match, as soon as it's found — from the scheduled daily search or a manual \"Find new matches\" click."}
            {form.notification_preference === "daily_digest" && "One summary a day listing everything found since your last digest, instead of one per match."}
            {form.notification_preference === "off" && "No alerts — matches will still show up on your Overview and Applications pages, you'll just need to check."}
          </p>
        </div>

        {form.notification_preference !== "off" && (
          <div className="field">
            <label>Send notifications via</label>
            <select
              value={form.notification_channel}
              onChange={(e) => {
                const channel = e.target.value;
                if ((channel === "sms" || channel === "both") && !form.sms_consent) {
                  alert("Check the SMS consent box below first, then pick this option again.");
                  return;
                }
                setForm({ ...form, notification_channel: channel });
              }}
            >
              <option value="email">Email only</option>
              <option value="sms">Text message only</option>
              <option value="both">Both</option>
            </select>
          </div>
        )}

        {form.notification_preference !== "off" && (
          <div className="field">
            <label style={{ display: "flex", alignItems: "flex-start", gap: 8, fontWeight: 400 }}>
              <input
                type="checkbox"
                checked={form.sms_consent}
                style={{ width: "auto", marginTop: 3 }}
                onChange={(e) => {
                  const consent = e.target.checked;
                  setForm({
                    ...form, sms_consent: consent,
                    // Dropping consent while SMS is the active channel
                    // falls back to email rather than leaving the form
                    // in a state the backend will reject on save.
                    notification_channel: consent ? form.notification_channel : "email",
                  });
                }}
              />
              <span>
                I agree to receive SMS text messages from Riseply about my job matches at the phone
                number above. Message and data rates may apply, frequency varies. Reply STOP at any
                time to unsubscribe. Consent isn't required to use Riseply — this only enables the
                text-message option above.
              </span>
            </label>
            {form.sms_consent && !form.phone.trim() && (
              <p className="hint" style={{ color: "var(--danger)" }}>Add a phone number above to actually enable SMS.</p>
            )}
          </div>
        )}

        {form.notification_preference !== "off" && (
          <div className="field">
            <label>Only notify me for matches at or above ({form.notification_min_score}%)</label>
            <input type="range" min={0} max={100} value={form.notification_min_score}
                   onChange={(e) => setForm({ ...form, notification_min_score: Number(e.target.value) })} />
            <p className="hint">
              A separate filter from your search profiles' own match threshold — this just controls
              which of the matches you already get notified about, not which ones show up at all.
              Leave at 0 to get notified about everything that clears your profile's own bar.
            </p>
          </div>
        )}

        {saved && <p style={{ color: "var(--accent)" }}>Saved.</p>}
        {error && <p className="error-text">{error}</p>}
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Auto-fill bookmarklet</h3>
        <p className="hint" style={{ marginTop: -4 }}>
          Runs entirely in your own browser, on the actual job application page you have open —
          fills in your name, email, phone, and links using your current profile info, fetched
          fresh each time. You'll still need to attach your resume and hit submit yourself;
          browsers don't let a script do either of those, on purpose.
        </p>

        <p style={{ fontWeight: 600, marginBottom: 4 }}>Option 1: copy the link (most reliable)</p>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button className="btn btn-ghost btn-sm" onClick={copyBookmarklet} disabled={!user?.bookmarklet_token}>
            {copied ? "Copied ✓" : "Copy auto-fill link"}
          </button>
        </div>
        <ol className="hint" style={{ marginTop: 8, paddingLeft: 18 }}>
          <li>Click the button above to copy the link.</li>
          <li>Right-click your browser's bookmarks bar and choose "Add page" (or click the ⭐ in your address bar, then edit it).</li>
          <li>Paste the copied link into the URL field, give it any name (e.g. "Riseply Auto-fill"), and save.</li>
          <li>
            If the pasted text is missing "javascript:" at the very start, some browsers strip it
            when you paste into a URL field as a security precaution — just retype "javascript:"
            at the beginning yourself and it'll work the same.
          </li>
        </ol>

        <p style={{ fontWeight: 600, marginTop: 16, marginBottom: 4 }}>Option 2: drag the button</p>
        {user?.bookmarklet_token && (
          <a
            href={buildAutoFillBookmarklet(user.bookmarklet_token, API_URL)}
            className="btn btn-ghost btn-sm"
            onClick={(e) => e.preventDefault()}
            draggable
          >
            📋 Riseply Auto-fill
          </a>
        )}
        <p className="hint" style={{ marginTop: 8 }}>
          Press and hold, then drag this button up onto your bookmarks bar — this works in most
          browsers, but if nothing shows up there afterward, use Option 1 instead. Clicking it here
          (rather than dragging) won't do anything, since there's no application form on this page.
        </p>

        <p className="hint" style={{ marginTop: 12 }}>
          Once it's saved as a bookmark, use it by going to a real job application page and
          clicking the bookmark from your bookmarks bar — not from here. Unlike before, it always
          pulls your current profile info when it runs, so you don't need to redo this after
          updating your profile.
        </p>

        <button
          className="btn btn-ghost btn-sm"
          style={{ marginTop: 12 }}
          onClick={async () => {
            if (!confirm("This invalidates any bookmarklet link you've already saved — you'll need to copy or drag a new one afterward. Continue?")) return;
            const updated = await api<User>("/me/regenerate-bookmarklet-token", { method: "POST" });
            setUser(updated);
          }}
        >
          Invalidate old links
        </button>
        <p className="hint" style={{ marginTop: 4 }}>
          If a bookmarklet link ever ends up somewhere it shouldn't (shared by accident, saved on
          a public computer), use this to cut it off — any bookmark made from the old link stops
          working immediately, without touching your password.
        </p>
      </div>
    </div>
  );
}
