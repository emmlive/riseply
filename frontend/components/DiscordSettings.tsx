"use client";

import { useEffect, useState } from "react";
import { api, DiscordStatus } from "@/lib/api";

// Connect Discord for "keep your momentum" messages: practice nudges,
// streak warnings, weekly recaps, session follow-ups, and (optionally)
// job matches. Delivery is through a webhook the person creates in their
// OWN Discord channel -- no Riseply bot to add. The URL is write-only:
// it's sent once on connect and never shown again (only a masked hint).

const HOURS = Array.from({ length: 24 }, (_, h) => h);
const hourLabel = (h: number) => `${((h + 11) % 12) + 1}:00 ${h < 12 ? "AM" : "PM"}`;

function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function timezoneList(current: string): string[] {
  let zones: string[] = [];
  try {
    zones = (Intl as any).supportedValuesOf?.("timeZone") ?? [];
  } catch { /* older browsers */ }
  if (zones.length === 0) zones = ["UTC", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "Europe/London", "Europe/Paris", "Asia/Kolkata", "Asia/Tokyo", "Australia/Sydney"];
  return zones.includes(current) ? zones : [current, ...zones];
}

export default function DiscordSettings() {
  const [status, setStatus] = useState<DiscordStatus | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [url, setUrl] = useState("");
  const [tz, setTz] = useState("UTC");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showGuide, setShowGuide] = useState(false);

  useEffect(() => {
    setTz(browserTimezone());
    api<DiscordStatus>("/discord")
      .then(setStatus)
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  async function connect() {
    if (!url.trim() || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const s = await api<DiscordStatus>("/discord/connect", {
        method: "PUT", body: JSON.stringify({ webhook_url: url.trim(), timezone: tz }),
      });
      setStatus(s);
      setUrl("");
      setNotice("Connected — check your Discord channel for a hello message.");
    } catch (err: any) {
      setError(/too many/i.test(err.message || "") ? "Too many attempts — please wait a while and try again." : (err.message || "Couldn't connect."));
    } finally {
      setBusy(false);
    }
  }

  async function update(patch: Partial<DiscordStatus>) {
    setError("");
    setNotice("");
    try {
      setStatus(await api<DiscordStatus>("/discord/settings", { method: "PATCH", body: JSON.stringify(patch) }));
    } catch (err: any) {
      setError(err.message || "Couldn't save that change.");
    }
  }

  async function sendTest() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api("/discord/test", { method: "POST" });
      setNotice("Test message sent — check Discord.");
    } catch (err: any) {
      setError(err.message || "Couldn't send the test message.");
      api<DiscordStatus>("/discord").then(setStatus).catch(() => {});
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!confirm("Disconnect Discord? You'll stop getting messages there. You can also delete the webhook in Discord.")) return;
    setBusy(true);
    try {
      await api("/discord", { method: "DELETE" });
      setStatus(null);
      setNotice("Disconnected.");
    } catch (err: any) {
      setError(err.message || "Couldn't disconnect.");
    } finally {
      setBusy(false);
    }
  }

  if (!loaded) return null;
  const connected = !!status?.connected;

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>Discord momentum</h3>
      <p className="hint" style={{ marginTop: -6 }}>
        Get friendly nudges to keep practicing, a heads-up before a streak breaks, a weekly recap, and
        a follow-up after each coaching session — right in Discord. It posts to a channel you choose
        (a private server just for you works great).
      </p>

      {error && <p className="error-text">{error}</p>}
      {notice && <p className="muted" style={{ color: "var(--accent-hover)" }}>{notice}</p>}

      {!connected && (
        <>
          <button className="btn btn-ghost btn-sm" onClick={() => setShowGuide((v) => !v)}>
            {showGuide ? "Hide setup steps" : "How do I get a webhook URL?"}
          </button>
          {showGuide && (
            <ol style={{ margin: "10px 0", paddingLeft: 20, fontSize: "0.9rem" }}>
              <li>In Discord, open the server and channel where you want messages (create a private server if you like).</li>
              <li>Click the gear next to the channel → <strong>Integrations</strong> → <strong>Webhooks</strong> → <strong>New Webhook</strong>.</li>
              <li>Click <strong>Copy Webhook URL</strong>, then paste it below.</li>
            </ol>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
            <input
              placeholder="https://discord.com/api/webhooks/…" value={url} maxLength={300}
              autoComplete="off" spellCheck={false}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") connect(); }}
            />
            <select value={tz} onChange={(e) => setTz(e.target.value)} aria-label="Your timezone">
              {timezoneList(tz).map((z) => <option key={z} value={z}>{z}</option>)}
            </select>
            <div>
              <button className="btn btn-primary btn-sm" onClick={connect} disabled={!url.trim() || busy}>
                {busy ? "Connecting…" : "Connect Discord"}
              </button>
            </div>
            <p className="hint" style={{ margin: 0 }}>
              We send a test message first. Anyone with this URL can post to that channel, so don&apos;t share it — we store it encrypted
              and never show it again.
            </p>
          </div>
        </>
      )}

      {connected && status && (
        <div>
          <div className="card-row" style={{ marginBottom: 8 }}>
            <div>
              <span className={status.enabled ? "pill pill-approved" : "pill pill-pending"}>{status.enabled ? "On" : "Off"}</span>{" "}
              <span className="hint mono">{status.webhook_hint}</span>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-ghost btn-sm" onClick={sendTest} disabled={busy}>Send test</button>
              <button className="btn btn-danger-ghost btn-sm" onClick={disconnect} disabled={busy}>Disconnect</button>
            </div>
          </div>

          {status.last_error && (
            <p className="error-text">
              {status.last_error}{" "}
              {!status.enabled && <button className="btn btn-ghost btn-sm" onClick={() => update({ enabled: true })}>Turn back on</button>}
            </p>
          )}

          {!status.enabled && !status.last_error && (
            <button className="btn btn-ghost btn-sm" onClick={() => update({ enabled: true })}>Turn back on</button>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8, opacity: status.enabled ? 1 : 0.55 }}>
            {([
              ["nudge_enabled", "Daily practice nudge", "A short reminder if you haven't practiced yet today, plus a heads-up when a streak is about to break."],
              ["progress_enabled", "Weekly recap", "Sundays: sessions finished, average score, and what to focus on next."],
              ["followup_enabled", "After each coaching session", "Your score, the one thing to work on next, and a Library resource."],
              ["matches_enabled", "New job matches", "Also post new matches (or your daily digest) here. Follows your match notification settings above."],
            ] as const).map(([key, label, hint]) => (
              <label key={key} style={{ display: "flex", alignItems: "flex-start", gap: 8, cursor: "pointer" }}>
                <input type="checkbox" style={{ width: "auto", marginTop: 3 }} checked={status[key]}
                       onChange={(e) => update({ [key]: e.target.checked } as Partial<DiscordStatus>)} />
                <span>
                  <div style={{ fontWeight: 600 }}>{label}</div>
                  <div className="hint">{hint}</div>
                </span>
              </label>
            ))}

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 4 }}>
              <span className="hint">Send my nudge around</span>
              <select value={status.nudge_hour} onChange={(e) => update({ nudge_hour: parseInt(e.target.value, 10) })} aria-label="Nudge time">
                {HOURS.map((h) => <option key={h} value={h}>{hourLabel(h)}</option>)}
              </select>
              <select value={status.timezone} onChange={(e) => update({ timezone: e.target.value })} aria-label="Timezone">
                {timezoneList(status.timezone).map((z) => <option key={z} value={z}>{z}</option>)}
              </select>
            </div>
            <p className="hint" style={{ margin: 0 }}>
              At most one nudge a day, and it only goes out if you haven&apos;t practiced yet. If you go quiet for a couple
              of weeks, it backs off on its own.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
