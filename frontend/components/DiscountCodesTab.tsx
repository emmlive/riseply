"use client";

import { useEffect, useState } from "react";
import { api, DiscountCode, DiscountRedemption } from "@/lib/api";

// Admin tab for creating and managing discount codes. Two kinds:
//   stripe    -- money off Pro at checkout (percent or dollars, for one
//                payment, N months, or forever); backed by Stripe.
//   free_days -- redeeming grants complimentary Pro for N days.
// Codes are never deleted, only disabled, so redemption history survives.

const STATUS_PILL: Record<string, string> = {
  active: "pill pill-approved", disabled: "pill pill-pending", expired: "pill pill-pending", exhausted: "pill pill-pending",
};

interface Draft {
  code: string;
  kind: "stripe" | "free_days";
  amountType: "percent" | "dollars";
  amount: string;
  duration: "once" | "repeating" | "forever";
  months: string;
  freeDays: string;
  max: string;
  expires: string; // yyyy-mm-dd, optional
  note: string;
}

const BLANK: Draft = {
  code: "", kind: "stripe", amountType: "percent", amount: "", duration: "once",
  months: "3", freeDays: "30", max: "", expires: "", note: "",
};

function fmtDate(iso: string | null) {
  return iso ? new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleDateString() : "—";
}

export default function DiscountCodesTab({ canAct }: { canAct: boolean }) {
  const [codes, setCodes] = useState<DiscountCode[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<Draft>(BLANK);
  const [saving, setSaving] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const [redemptions, setRedemptions] = useState<DiscountRedemption[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);

  async function load() {
    try {
      setCodes(await api<DiscountCode[]>("/admin/discount-codes"));
    } catch (err: any) {
      setError(err.message || "Couldn't load discount codes.");
    } finally {
      setLoaded(true);
    }
  }
  useEffect(() => { load(); }, []);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft((d) => ({ ...d, [k]: v }));

  function buildBody() {
    const body: Record<string, unknown> = { code: draft.code.trim(), kind: draft.kind, note: draft.note.trim() };
    if (draft.kind === "free_days") {
      body.free_days = parseInt(draft.freeDays, 10);
    } else {
      if (draft.amountType === "percent") body.percent_off = parseInt(draft.amount, 10);
      else body.amount_off_cents = Math.round(parseFloat(draft.amount) * 100);
      body.duration = draft.duration;
      if (draft.duration === "repeating") body.duration_months = parseInt(draft.months, 10);
    }
    if (draft.max.trim()) body.max_redemptions = parseInt(draft.max, 10);
    // Expire at the END of the chosen day (UTC) so "through Dec 31" means it.
    if (draft.expires) body.expires_at = `${draft.expires}T23:59:59`;
    return body;
  }

  async function create() {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      await api("/admin/discount-codes", { method: "POST", body: JSON.stringify(buildBody()) });
      setCreating(false);
      setDraft(BLANK);
      await load();
    } catch (err: any) {
      setError(err.message || "Couldn't create that code.");
    } finally {
      setSaving(false);
    }
  }

  async function toggle(c: DiscountCode) {
    setBusyId(c.id);
    setError("");
    try {
      await api(`/admin/discount-codes/${c.id}/active`, { method: "POST", body: JSON.stringify({ active: !c.active }) });
      await load();
    } catch (err: any) {
      setError(err.message || "Couldn't update that code.");
    } finally {
      setBusyId(null);
    }
  }

  async function showRedemptions(c: DiscountCode) {
    if (openId === c.id) { setOpenId(null); return; }
    setOpenId(c.id);
    setRedemptions([]);
    try {
      setRedemptions(await api<DiscountRedemption[]>(`/admin/discount-codes/${c.id}/redemptions`));
    } catch (err: any) {
      setError(err.message || "Couldn't load redemptions.");
    }
  }

  const valid =
    draft.code.trim().length >= 3 &&
    (draft.kind === "free_days" ? parseInt(draft.freeDays, 10) > 0 : parseFloat(draft.amount) > 0);

  return (
    <div>
      {error && <p className="error-text">{error}</p>}

      <div className="card">
        <div className="card-row">
          <div>
            <h3 style={{ margin: 0 }}>Discount codes</h3>
            <p className="hint" style={{ margin: "4px 0 0" }}>
              Money-off codes are applied at Stripe checkout. Free-days codes give Pro with no payment.
            </p>
          </div>
          {canAct && !creating && <button className="btn btn-primary btn-sm" onClick={() => setCreating(true)}>New code</button>}
        </div>

        {creating && (
          <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
            <input placeholder="Code people will type (e.g. LAUNCH50)" value={draft.code} maxLength={30}
                   onChange={(e) => set("code", e.target.value.replace(/[^A-Za-z0-9_-]/g, ""))} />
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
              <label><input type="radio" checked={draft.kind === "stripe"} onChange={() => set("kind", "stripe")} /> Money off Pro at checkout</label>
              <label><input type="radio" checked={draft.kind === "free_days"} onChange={() => set("kind", "free_days")} /> Free Pro days (no card)</label>
            </div>

            {draft.kind === "stripe" ? (
              <>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                  <select value={draft.amountType} onChange={(e) => set("amountType", e.target.value as Draft["amountType"])}>
                    <option value="percent">Percent off</option>
                    <option value="dollars">Dollars off</option>
                  </select>
                  <input style={{ width: 110 }} type="number" min={1} step={draft.amountType === "percent" ? 1 : 0.5}
                         max={draft.amountType === "percent" ? 100 : undefined}
                         placeholder={draft.amountType === "percent" ? "e.g. 25" : "e.g. 5.00"}
                         value={draft.amount} onChange={(e) => set("amount", e.target.value)} />
                  <span className="hint">{draft.amountType === "percent" ? "%" : "USD"}</span>
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                  <span className="hint">Applies to</span>
                  <select value={draft.duration} onChange={(e) => set("duration", e.target.value as Draft["duration"])}>
                    <option value="once">first payment only</option>
                    <option value="repeating">a number of months</option>
                    <option value="forever">every payment, forever</option>
                  </select>
                  {draft.duration === "repeating" && (
                    <>
                      <input style={{ width: 80 }} type="number" min={1} max={36} value={draft.months}
                             onChange={(e) => set("months", e.target.value)} />
                      <span className="hint">months</span>
                    </>
                  )}
                </div>
              </>
            ) : (
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span className="hint">Grants</span>
                <input style={{ width: 90 }} type="number" min={1} max={365} value={draft.freeDays}
                       onChange={(e) => set("freeDays", e.target.value)} />
                <span className="hint">days of Pro</span>
              </div>
            )}

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <input style={{ width: 170 }} type="number" min={1} placeholder="Max uses (optional)" value={draft.max}
                     onChange={(e) => set("max", e.target.value)} />
              <label className="hint" style={{ display: "flex", gap: 6, alignItems: "center" }}>
                Expires (optional)
                <input type="date" value={draft.expires} onChange={(e) => set("expires", e.target.value)} />
              </label>
            </div>
            <input placeholder="Internal note (optional — who it's for)" value={draft.note} maxLength={200}
                   onChange={(e) => set("note", e.target.value)} />
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-primary btn-sm" onClick={create} disabled={!valid || saving}>
                {saving ? "Creating…" : "Create code"}
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => { setCreating(false); setDraft(BLANK); }}>Cancel</button>
            </div>
          </div>
        )}
      </div>

      {loaded && codes.length === 0 && <p className="hint">No discount codes yet.</p>}

      {codes.map((c) => (
        <div key={c.id} className="card" style={{ opacity: c.status === "active" ? 1 : 0.8 }}>
          <div className="card-row">
            <div>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <strong className="mono">{c.code}</strong>
                <span className={STATUS_PILL[c.status] || "pill"}>{c.status}</span>
                <span className="hint">{c.kind === "free_days" ? "free days" : "checkout discount"}</span>
              </div>
              <div>{c.description}</div>
              <div className="hint">
                Used {c.redemption_count}{c.max_redemptions ? ` of ${c.max_redemptions}` : ""} · Expires {fmtDate(c.expires_at)}
                {c.note ? ` · ${c.note}` : ""}
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => showRedemptions(c)}>
                {openId === c.id ? "Hide users" : "Who used it"}
              </button>
              {canAct && (
                <button className="btn btn-ghost btn-sm" onClick={() => toggle(c)} disabled={busyId === c.id}>
                  {c.active ? "Disable" : "Enable"}
                </button>
              )}
            </div>
          </div>
          {openId === c.id && (
            <div style={{ marginTop: 10 }}>
              {redemptions.length === 0 ? (
                <p className="hint" style={{ margin: 0 }}>Nobody has used this code yet.</p>
              ) : redemptions.map((r, i) => (
                <div key={i} className="points-event-row">
                  <div>{r.email}</div>
                  <div className="hint">{r.detail} · {fmtDate(r.redeemed_at)}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
