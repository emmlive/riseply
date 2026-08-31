"use client";

import { useEffect, useRef, useState } from "react";
import { api, downloadFile, API_URL, Organization, OrgContent, OrgUsageStats, OrgAnalytics, OrgRosterEntry, OrgBilling, OrgContact, OrgEmployee, OrgSSOConfig, Department, ChecklistItem, OrgLesson, OrgQALog, User, SuggestedMentor, MentorMeetingLog } from "@/lib/api";
import MediaEmbed from "@/components/MediaEmbed";

export default function OrgBuddyPage() {
  const [orgs, setOrgs] = useState<Organization[] | null>(null);
  const [selected, setSelected] = useState<Organization | null>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [creatingSandbox, setCreatingSandbox] = useState(false);

  function load() {
    api<Organization[]>("/orgs/mine").then((orgList) => {
      setOrgs(orgList);
      if (orgList.length > 0 && !selected) {
        // Supports deep-linking to a specific org, e.g. from the Admin
        // panel's Sandbox orgs list (?org=<id>) -- falls back to the
        // first org if there's no match or no param.
        const params = new URLSearchParams(window.location.search);
        const requestedId = params.get("org");
        const requested = requestedId ? orgList.find((o) => o.id === Number(requestedId)) : null;
        setSelected(requested || orgList[0]);
      }
    });
  }

  useEffect(() => {
    load();
    api<User>("/me").then(setUser).catch(() => {});
  }, []);

  async function createOrg() {
    setCreating(true);
    setError("");
    try {
      const org = await api<Organization>("/orgs", { method: "POST", body: JSON.stringify({ name }) });
      setName("");
      load();
      setSelected(org);
    } catch (err: any) {
      setError(err.message || "Couldn't create the organization.");
    } finally {
      setCreating(false);
    }
  }

  async function createSandbox() {
    setCreatingSandbox(true);
    setError("");
    try {
      const org = await api<Organization>("/orgs/sandbox", { method: "POST" });
      load();
      setSelected(org);
    } catch (err: any) {
      setError(err.message || "Couldn't create a sandbox.");
    } finally {
      setCreatingSandbox(false);
    }
  }

  if (orgs === null) return <p className="muted">Loading…</p>;

  const hasSandbox = orgs.some((o) => o.is_sandbox);

  return (
    <div>
      <h1>Org Buddy</h1>
      <p className="muted">
        Your company's own onboarding buddy — the traditional practice of
        pairing new hires with support for their first stretch, grounded
        in your actual handbook, culture, and team info instead of
        generic advice. Employee conversations stay private; you see
        that it's working, not what anyone said.
      </p>

      {orgs.length === 0 && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Set up your organization</h3>
          <div className="field">
            <label>Company name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          {error && <p className="error-text">{error}</p>}
          <button className="btn btn-primary btn-sm" onClick={createOrg} disabled={creating || !name.trim()}>
            {creating ? "Creating…" : "Create organization"}
          </button>
        </div>
      )}

      {user?.is_admin && !hasSandbox && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Try it yourself</h3>
          <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
            A personal sandbox org, just for you — real Org Buddy, Culture Bot, and Ghost
            Onboarder features, but never a real customer's account. Not billed, and excluded
            from revenue and seat totals in the Admin panel.
          </p>
          {error && <p className="error-text">{error}</p>}
          <button className="btn btn-ghost btn-sm" onClick={createSandbox} disabled={creatingSandbox}>
            {creatingSandbox ? "Creating…" : "Create my sandbox"}
          </button>
        </div>
      )}

      {orgs.length > 0 && selected && (
        <OrgDashboard org={selected} orgs={orgs} onSwitch={setSelected} />
      )}
    </div>
  );
}

function OrgDashboard({ org, orgs, onSwitch }: { org: Organization; orgs: Organization[]; onSwitch: (o: Organization) => void }) {
  const [content, setContent] = useState<OrgContent[]>([]);
  const [stats, setStats] = useState<OrgUsageStats | null>(null);
  const [analytics, setAnalytics] = useState<OrgAnalytics | null>(null);
  const [roster, setRoster] = useState<OrgRosterEntry[]>([]);
  const [billing, setBilling] = useState<OrgBilling | null>(null);
  const [showEnterpriseBillingForm, setShowEnterpriseBillingForm] = useState(false);
  const [ebContactName, setEbContactName] = useState("");
  const [ebContactEmail, setEbContactEmail] = useState("");
  const [ebEmployeeCount, setEbEmployeeCount] = useState("0");
  const [ebNotes, setEbNotes] = useState("");
  const [ebSending, setEbSending] = useState(false);
  const [ebError, setEbError] = useState("");
  const [enterpriseBillingSent, setEnterpriseBillingSent] = useState("");
  const [ssoConfig, setSsoConfig] = useState<OrgSSOConfig | null>(null);
  const [showSsoForm, setShowSsoForm] = useState(false);
  const [ssoProviderName, setSsoProviderName] = useState("");
  const [ssoIssuer, setSsoIssuer] = useState("");
  const [ssoClientId, setSsoClientId] = useState("");
  const [ssoClientSecret, setSsoClientSecret] = useState("");
  const [ssoDomain, setSsoDomain] = useState("");
  const [ssoSaving, setSsoSaving] = useState(false);
  const [ssoError, setSsoError] = useState("");
  const [ssoLinkCopied, setSsoLinkCopied] = useState(false);
  const [contacts, setContacts] = useState<OrgContact[]>([]);
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactDesc, setContactDesc] = useState("");
  const [contactDept, setContactDept] = useState<string>("");
  const [contactIsMentor, setContactIsMentor] = useState(false);
  const [contactMentorBio, setContactMentorBio] = useState("");
  const [addingContact, setAddingContact] = useState(false);
  const [contactError, setContactError] = useState("");
  const [employees, setEmployees] = useState<OrgEmployee[]>([]);
  const [assigningEmployeeId, setAssigningEmployeeId] = useState<number | null>(null);
  // AI mentor suggestions -- keyed by application_id so multiple
  // employees' suggestion panels can be open independently.
  const [suggestingFor, setSuggestingFor] = useState<number | null>(null);
  const [suggestions, setSuggestions] = useState<Record<number, SuggestedMentor[]>>({});
  // Meeting log panel -- keyed by mentor_assignment_id, same reasoning.
  const [meetingLogOpenFor, setMeetingLogOpenFor] = useState<number | null>(null);
  const [meetings, setMeetings] = useState<Record<number, MentorMeetingLog[]>>({});
  const [newMeetingDate, setNewMeetingDate] = useState("");
  const [newMeetingNotes, setNewMeetingNotes] = useState("");
  const [loggingMeeting, setLoggingMeeting] = useState(false);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [deptName, setDeptName] = useState("");
  const [addingDept, setAddingDept] = useState(false);
  const [deptError, setDeptError] = useState("");
  const [logoUrl, setLogoUrl] = useState(org.logo_url);
  const [savingLogo, setSavingLogo] = useState(false);
  const [logoError, setLogoError] = useState("");
  const [contentDept, setContentDept] = useState<string>("");
  const [contentMediaUrl, setContentMediaUrl] = useState("");
  const [checklist, setChecklist] = useState<ChecklistItem[]>([]);
  const [checklistTitle, setChecklistTitle] = useState("");
  const [checklistDept, setChecklistDept] = useState<string>("");
  const [checklistPolicy, setChecklistPolicy] = useState("");
  const [checklistMediaUrl, setChecklistMediaUrl] = useState("");
  const [addingChecklistItem, setAddingChecklistItem] = useState(false);
  const [checklistError, setChecklistError] = useState("");
  const [lessons, setLessons] = useState<OrgLesson[]>([]);
  const [lessonDay, setLessonDay] = useState("0");
  const [lessonTitle, setLessonTitle] = useState("");
  const [lessonContent, setLessonContent] = useState("");
  const [lessonQuizQ, setLessonQuizQ] = useState("");
  const [lessonQuizA, setLessonQuizA] = useState("");
  const [lessonDept, setLessonDept] = useState<string>("");
  const [lessonMediaUrl, setLessonMediaUrl] = useState("");
  const [addingLesson, setAddingLesson] = useState(false);
  const [lessonError, setLessonError] = useState("");
  const [qaLogs, setQaLogs] = useState<OrgQALog[] | null>(null);
  const [qaFilter, setQaFilter] = useState<"all" | "unmatched">("unmatched");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [rosterUploading, setRosterUploading] = useState(false);
  const [rosterResult, setRosterResult] = useState<{ added: number; updated: number; errors: string[] } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function load() {
    api<OrgContent[]>(`/orgs/${org.id}/content`).then(setContent);
    // Usage stats and billing are org-wide-admin-only on the backend --
    // a department admin correctly gets a 403 on these two specifically
    // (billing and aggregate usage across every department are legitimately
    // out of their scope), so both need to fail silently here rather than
    // surface as an error toast, and the cards themselves stay hidden
    // rather than rendering an empty shell.
    api<OrgUsageStats>(`/orgs/${org.id}/usage`).then(setStats).catch(() => {});
    api<OrgAnalytics>(`/orgs/${org.id}/analytics`).then(setAnalytics).catch(() => {});
    api<OrgSSOConfig | null>(`/orgs/${org.id}/sso-config`).then(setSsoConfig).catch(() => {});
    api<OrgRosterEntry[]>(`/orgs/${org.id}/roster`).then(setRoster);
    api<OrgBilling>(`/orgs/${org.id}/billing`).then(setBilling).catch(() => {});
    api<OrgContact[]>(`/orgs/${org.id}/contacts`).then(setContacts);
    api<OrgEmployee[]>(`/orgs/${org.id}/employees`).then(setEmployees).catch(() => {});
    api<Department[]>(`/orgs/${org.id}/departments`).then(setDepartments);
    api<ChecklistItem[]>(`/orgs/${org.id}/checklist`).then(setChecklist);
    api<OrgLesson[]>(`/orgs/${org.id}/lessons`).then(setLessons);
    // Org-wide-admin-only, same as usage/billing above -- fails silently
    // for a department admin rather than surfacing an error toast.
    api<OrgQALog[]>(`/orgs/${org.id}/qa-logs?unmatched_only=${qaFilter === "unmatched"}`).then(setQaLogs).catch(() => setQaLogs(null));
  }

  useEffect(() => { load(); setLogoUrl(org.logo_url); }, [org.id, qaFilter]);

  async function addContent() {
    setAdding(true);
    setError("");
    try {
      await api(`/orgs/${org.id}/content`, {
        method: "POST",
        body: JSON.stringify({
          title, content: body,
          department_id: contentDept ? Number(contentDept) : null,
          media_url: contentMediaUrl.trim(),
        }),
      });
      setTitle(""); setBody(""); setContentMediaUrl("");
      load();
    } catch (err: any) {
      setError(err.message || "Couldn't add that content.");
    } finally {
      setAdding(false);
    }
  }

  async function addDepartment() {
    setAddingDept(true);
    setDeptError("");
    try {
      await api(`/orgs/${org.id}/departments`, { method: "POST", body: JSON.stringify({ name: deptName }) });
      setDeptName("");
      load();
    } catch (err: any) {
      setDeptError(err.message || "Couldn't add that department.");
    } finally {
      setAddingDept(false);
    }
  }

  async function addChecklistItem() {
    setAddingChecklistItem(true);
    setChecklistError("");
    try {
      await api(`/orgs/${org.id}/checklist`, {
        method: "POST",
        body: JSON.stringify({
          title: checklistTitle,
          department_id: checklistDept ? Number(checklistDept) : null,
          policy_content: checklistPolicy.trim() || null,
          media_url: checklistMediaUrl.trim(),
          order: checklist.length,
        }),
      });
      setChecklistTitle(""); setChecklistPolicy(""); setChecklistMediaUrl("");
      load();
    } catch (err: any) {
      setChecklistError(err.message || "Couldn't add that item.");
    } finally {
      setAddingChecklistItem(false);
    }
  }

  async function removeChecklistItem(itemId: number) {
    await api(`/orgs/${org.id}/checklist/${itemId}`, { method: "DELETE" });
    load();
  }

  async function addLesson() {
    setAddingLesson(true);
    setLessonError("");
    try {
      await api(`/orgs/${org.id}/lessons`, {
        method: "POST",
        body: JSON.stringify({
          day_offset: Number(lessonDay) || 0,
          title: lessonTitle,
          content: lessonContent,
          quiz_question: lessonQuizQ.trim(),
          quiz_answer: lessonQuizA.trim(),
          department_id: lessonDept ? Number(lessonDept) : null,
          media_url: lessonMediaUrl.trim(),
          order: lessons.length,
        }),
      });
      setLessonDay("0"); setLessonTitle(""); setLessonContent(""); setLessonQuizQ(""); setLessonQuizA(""); setLessonMediaUrl("");
      load();
    } catch (err: any) {
      setLessonError(err.message || "Couldn't add that lesson.");
    } finally {
      setAddingLesson(false);
    }
  }

  async function removeLesson(lessonId: number) {
    await api(`/orgs/${org.id}/lessons/${lessonId}`, { method: "DELETE" });
    load();
  }

  async function saveLogo() {
    setSavingLogo(true);
    setLogoError("");
    try {
      await api(`/orgs/${org.id}/settings`, { method: "PUT", body: JSON.stringify({ logo_url: logoUrl }) });
    } catch (err: any) {
      setLogoError(err.message || "Couldn't save that logo URL.");
    } finally {
      setSavingLogo(false);
    }
  }

  async function removeContent(contentId: number) {
    await api(`/orgs/${org.id}/content/${contentId}`, { method: "DELETE" });
    load();
  }

  async function uploadRoster(file: File) {
    setRosterUploading(true);
    setRosterResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const result = await api<{ added: number; updated: number; errors: string[] }>(
        `/orgs/${org.id}/roster/upload`, { method: "POST", body: formData }
      );
      setRosterResult(result);
      load();
    } catch (err: any) {
      setRosterResult({ added: 0, updated: 0, errors: [err.message || "Upload failed."] });
    } finally {
      setRosterUploading(false);
    }
  }

  async function subscribe(plan: "starter" | "growth") {
    try {
      const { checkout_url } = await api<{ checkout_url: string }>(
        `/orgs/${org.id}/subscribe?plan=${plan}`, { method: "POST" }
      );
      window.location.href = checkout_url;
    } catch (err: any) {
      alert(err.message || "Couldn't start checkout.");
    }
  }

  async function submitEnterpriseBilling() {
    if (!ebContactName.trim() || !ebContactEmail.trim()) return;
    setEbSending(true);
    setEbError("");
    try {
      await api(`/orgs/${org.id}/request-enterprise-billing`, {
        method: "POST",
        body: JSON.stringify({
          billing_contact_name: ebContactName.trim(),
          billing_contact_email: ebContactEmail.trim(),
          estimated_employees: Number(ebEmployeeCount) || 0,
          notes: ebNotes.trim(),
        }),
      });
      setShowEnterpriseBillingForm(false);
      setEnterpriseBillingSent("Sent — we'll follow up directly to set up invoicing.");
      setEbContactName(""); setEbContactEmail(""); setEbEmployeeCount("0"); setEbNotes("");
    } catch (err: any) {
      setEbError(err.message || "Couldn't send that request.");
    } finally {
      setEbSending(false);
    }
  }

  async function saveSsoConfig() {
    if (!ssoIssuer.trim() || !ssoClientId.trim() || !ssoClientSecret.trim() || !ssoDomain.trim()) return;
    setSsoSaving(true);
    setSsoError("");
    try {
      const saved = await api<OrgSSOConfig>(`/orgs/${org.id}/sso-config`, {
        method: "POST",
        body: JSON.stringify({
          provider_name: ssoProviderName.trim(),
          issuer: ssoIssuer.trim(),
          client_id: ssoClientId.trim(),
          client_secret: ssoClientSecret.trim(),
          allowed_email_domain: ssoDomain.trim(),
        }),
      });
      setSsoConfig(saved);
      setShowSsoForm(false);
      setSsoClientSecret(""); // never linger in state once saved
    } catch (err: any) {
      setSsoError(err.message || "Couldn't save that SSO configuration.");
    } finally {
      setSsoSaving(false);
    }
  }

  async function removeSsoConfig() {
    if (!confirm("Remove SSO for this organization? Employees will need to sign in the normal way afterward.")) return;
    try {
      await api(`/orgs/${org.id}/sso-config`, { method: "DELETE" });
      setSsoConfig(null);
    } catch (err: any) {
      alert(err.message || "Couldn't remove that.");
    }
  }

  function copySsoLink() {
    const link = `${API_URL}/auth/sso/${org.id}/login`;
    navigator.clipboard.writeText(link).then(() => {
      setSsoLinkCopied(true);
      setTimeout(() => setSsoLinkCopied(false), 2000);
    });
  }

  async function addContact() {
    setAddingContact(true);
    setContactError("");
    try {
      await api(`/orgs/${org.id}/contacts`, {
        method: "POST",
        body: JSON.stringify({
          name: contactName, email: contactEmail, description: contactDesc,
          department_id: contactDept ? Number(contactDept) : null,
          is_mentor: contactIsMentor, mentor_bio: contactMentorBio,
        }),
      });
      setContactName(""); setContactEmail(""); setContactDesc(""); setContactIsMentor(false); setContactMentorBio("");
      load();
    } catch (err: any) {
      setContactError(err.message || "Couldn't add that contact.");
    } finally {
      setAddingContact(false);
    }
  }

  async function assignMentor(applicationId: number, contactId: number) {
    setAssigningEmployeeId(applicationId);
    try {
      await api(`/orgs/${org.id}/employees/${applicationId}/assign-mentor`, {
        method: "POST", body: JSON.stringify({ contact_id: contactId }),
      });
      load();
    } catch (err: any) {
      alert(err.message || "Couldn't assign that mentor.");
    } finally {
      setAssigningEmployeeId(null);
    }
  }

  async function loadSuggestedMentors(applicationId: number) {
    if (suggestingFor === applicationId) {
      setSuggestingFor(null);  // toggle closed if already open
      return;
    }
    setSuggestingFor(applicationId);
    try {
      const ranked = await api<SuggestedMentor[]>(`/orgs/${org.id}/employees/${applicationId}/suggested-mentors`);
      setSuggestions((prev) => ({ ...prev, [applicationId]: ranked }));
    } catch (err: any) {
      alert(err.message || "Couldn't get mentor suggestions.");
      setSuggestingFor(null);
    }
  }

  async function loadMeetings(assignmentId: number) {
    if (meetingLogOpenFor === assignmentId) {
      setMeetingLogOpenFor(null);
      return;
    }
    setMeetingLogOpenFor(assignmentId);
    setNewMeetingDate(""); setNewMeetingNotes("");
    try {
      const rows = await api<MentorMeetingLog[]>(`/orgs/${org.id}/mentor-assignments/${assignmentId}/meetings`);
      setMeetings((prev) => ({ ...prev, [assignmentId]: rows }));
    } catch (err: any) {
      alert(err.message || "Couldn't load meeting history.");
    }
  }

  async function logMeeting(assignmentId: number) {
    if (!newMeetingDate) return;
    setLoggingMeeting(true);
    try {
      await api(`/orgs/${org.id}/mentor-assignments/${assignmentId}/meetings`, {
        method: "POST",
        body: JSON.stringify({ meeting_date: newMeetingDate, notes: newMeetingNotes }),
      });
      setNewMeetingDate(""); setNewMeetingNotes("");
      const rows = await api<MentorMeetingLog[]>(`/orgs/${org.id}/mentor-assignments/${assignmentId}/meetings`);
      setMeetings((prev) => ({ ...prev, [assignmentId]: rows }));
    } catch (err: any) {
      alert(err.message || "Couldn't log that meeting.");
    } finally {
      setLoggingMeeting(false);
    }
  }

  async function removeContactEntry(contactId: number) {
    await api(`/orgs/${org.id}/contacts/${contactId}`, { method: "DELETE" });
    load();
  }

  return (
    <div>
      {orgs.length > 1 && (
        <select value={org.id} onChange={(e) => onSwitch(orgs.find((o) => o.id === Number(e.target.value))!)}
                style={{ marginBottom: 16, width: "auto" }}>
          {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
      )}

      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {logoUrl && (
            <img src={logoUrl} alt="" style={{ width: 40, height: 40, objectFit: "contain", borderRadius: 6 }}
                 onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
          )}
          <h3 style={{ margin: 0 }}>
            {org.name}
            {org.is_sandbox && <span className="pill pill-default" style={{ marginLeft: 8 }}>Sandbox</span>}
          </h3>
        </div>
        {org.is_sandbox && (
          <p className="hint" style={{ marginTop: 8, marginBottom: 8 }}>
            Personal pilot access — not a real customer, can't be billed, and excluded from Admin panel totals.
          </p>
        )}
        <p className="muted" style={{ marginBottom: 4, marginTop: 12 }}>Join code — share this with new hires:</p>
        <span className="mono" style={{ fontSize: "1.3rem", fontWeight: 700, letterSpacing: 2 }}>{org.join_code}</span>

        <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
          <label style={{ display: "block", marginBottom: 4 }}>Logo URL (optional)</label>
          <p className="hint" style={{ marginTop: -2, marginBottom: 8 }}>
            Shown here and to your employees on their onboarding pages. Paste a link to an
            already-hosted image — there's no upload yet, just a URL.
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <input value={logoUrl} onChange={(e) => setLogoUrl(e.target.value)}
                   placeholder="https://yourcompany.com/logo.png" style={{ flex: 1 }} />
            <button className="btn btn-ghost btn-sm" onClick={saveLogo} disabled={savingLogo}>
              {savingLogo ? "Saving…" : "Save"}
            </button>
          </div>
          {logoError && <p className="error-text">{logoError}</p>}
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Departments</h3>
        <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
          Each department gets its own join code. Someone joining with a department's code sees
          company-wide content plus that department's own material layered on top.
        </p>
        {departments.map((d) => (
          <div key={d.id} className="points-event-row">
            <div style={{ fontWeight: 600 }}>{d.name}</div>
            <span className="mono hint">{d.join_code}</span>
          </div>
        ))}
        <div style={{ display: "flex", gap: 8, marginTop: departments.length > 0 ? 16 : 0 }}>
          <input value={deptName} onChange={(e) => setDeptName(e.target.value)}
                 placeholder="e.g. Finance" style={{ flex: 1 }} />
          <button className="btn btn-primary btn-sm" onClick={addDepartment} disabled={addingDept || !deptName.trim()}>
            {addingDept ? "Adding…" : "Add department"}
          </button>
        </div>
        {deptError && <p className="error-text">{deptError}</p>}
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Onboarding checklist</h3>
        <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
          Employees check these off themselves as they go. Once every applicable
          item is done, the employee's manager (if on file via the roster) gets
          a factual completion notice — never any conversation content.
        </p>
        {checklist.map((c) => (
          <div key={c.id} className="points-event-row" style={{ flexDirection: "column", alignItems: "stretch" }}>
            <div style={{ display: "flex", justifyContent: "space-between", width: "100%" }}>
              <div style={{ fontWeight: 600 }}>
                {c.title}
                {c.policy_content && <span className="pill pill-default" style={{ marginLeft: 8 }}>Policy acknowledgment</span>}
                {c.department_id && (
                  <span className="hint" style={{ marginLeft: 8 }}>
                    ({departments.find((d) => d.id === c.department_id)?.name || "Department"})
                  </span>
                )}
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => removeChecklistItem(c.id)}>Remove</button>
            </div>
            {c.media_url && <MediaEmbed url={c.media_url} />}
          </div>
        ))}
        <div style={{ marginTop: checklist.length > 0 ? 16 : 0 }}>
          <div style={{ display: "flex", gap: 8 }}>
            <input value={checklistTitle} onChange={(e) => setChecklistTitle(e.target.value)}
                   placeholder="e.g. Set up your laptop" style={{ flex: 1 }} />
            {departments.length > 0 && (
              <select value={checklistDept} onChange={(e) => setChecklistDept(e.target.value)} style={{ width: 180 }}>
                <option value="">Company-wide</option>
                {departments.map((d) => <option key={d.id} value={d.id}>{d.name} only</option>)}
              </select>
            )}
          </div>
          <div className="field" style={{ marginTop: 8 }}>
            <label>Policy text (optional)</label>
            <textarea rows={3} value={checklistPolicy} onChange={(e) => setChecklistPolicy(e.target.value)}
                      placeholder="If set, the employee must read this exact text before they can acknowledge it — used for things like a Code of Ethics or anti-harassment policy. Leave blank for a plain task item." />
          </div>
          <div className="field" style={{ marginTop: 8 }}>
            <label>Media link (optional)</label>
            <input value={checklistMediaUrl} onChange={(e) => setChecklistMediaUrl(e.target.value)}
                   placeholder="https://youtube.com/watch?v=... or a link to a hosted image/document" />
          </div>
          <button className="btn btn-primary btn-sm" onClick={addChecklistItem}
                  disabled={addingChecklistItem || !checklistTitle.trim()} style={{ marginTop: 8 }}>
            {addingChecklistItem ? "Adding…" : "Add item"}
          </button>
        </div>
        {checklistError && <p className="error-text">{checklistError}</p>}
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Culture Bot lessons</h3>
        <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
          Short lessons delivered by email on a schedule relative to each employee's join date —
          spaced-repetition instead of an 8-hour Day 1 orientation. Add an optional quiz question;
          a wrong answer gets a follow-up reminder a week later.
        </p>
        {lessons.map((l) => (
          <div key={l.id} className="points-event-row" style={{ flexDirection: "column", alignItems: "stretch" }}>
            <div style={{ display: "flex", justifyContent: "space-between", width: "100%" }}>
              <div>
                <div style={{ fontWeight: 600 }}>
                  Day {l.day_offset}: {l.title}
                  {l.quiz_question && <span className="pill pill-default" style={{ marginLeft: 8 }}>Has quiz</span>}
                  {l.department_id && (
                    <span className="hint" style={{ marginLeft: 8 }}>
                      ({departments.find((d) => d.id === l.department_id)?.name || "Department"})
                    </span>
                  )}
                </div>
                <div className="hint">{l.content}</div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => removeLesson(l.id)}>Remove</button>
            </div>
            {l.media_url && <MediaEmbed url={l.media_url} />}
          </div>
        ))}
        <div style={{ marginTop: lessons.length > 0 ? 16 : 0 }}>
          <div style={{ display: "flex", gap: 8 }}>
            <input type="number" min={0} value={lessonDay} onChange={(e) => setLessonDay(e.target.value)}
                   placeholder="Day" style={{ width: 80 }} />
            <input value={lessonTitle} onChange={(e) => setLessonTitle(e.target.value)}
                   placeholder="e.g. Expense policy" style={{ flex: 1 }} />
            {departments.length > 0 && (
              <select value={lessonDept} onChange={(e) => setLessonDept(e.target.value)} style={{ width: 180 }}>
                <option value="">Company-wide</option>
                {departments.map((d) => <option key={d.id} value={d.id}>{d.name} only</option>)}
              </select>
            )}
          </div>
          <div className="field" style={{ marginTop: 8 }}>
            <label>Lesson content</label>
            <textarea rows={3} value={lessonContent} onChange={(e) => setLessonContent(e.target.value)}
                      placeholder="Submit expenses via the Expensify app within 30 days of purchase." />
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <input value={lessonQuizQ} onChange={(e) => setLessonQuizQ(e.target.value)}
                   placeholder="Quiz question (optional)" style={{ flex: 1 }} />
            <input value={lessonQuizA} onChange={(e) => setLessonQuizA(e.target.value)}
                   placeholder="Expected answer" style={{ flex: 1 }} />
          </div>
          <div className="field" style={{ marginTop: 8 }}>
            <label>Media link (optional)</label>
            <input value={lessonMediaUrl} onChange={(e) => setLessonMediaUrl(e.target.value)}
                   placeholder="https://youtube.com/watch?v=... or a link to a hosted image/document" />
          </div>
          <button className="btn btn-primary btn-sm" onClick={addLesson}
                  disabled={addingLesson || !lessonTitle.trim() || !lessonContent.trim()} style={{ marginTop: 8 }}>
            {addingLesson ? "Adding…" : "Add lesson"}
          </button>
        </div>
        {lessonError && <p className="error-text">{lessonError}</p>}
      </div>

      {qaLogs !== null && (
        <div className="card">
          <div className="card-row">
            <h3 style={{ margin: 0 }}>What employees are asking (Ghost Onboarder)</h3>
          </div>
          <p className="hint" style={{ marginTop: 4, marginBottom: 12 }}>
            Instant Q&A answered from your uploaded content above. Questions marked
            "not covered" are the clearest signal for what to add next.
          </p>
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            {(["unmatched", "all"] as const).map((f) => (
              <button
                key={f}
                className="btn btn-ghost btn-sm"
                style={qaFilter === f ? { background: "var(--accent-soft)", color: "var(--accent-hover)", borderColor: "var(--accent)" } : {}}
                onClick={() => setQaFilter(f)}
              >
                {f === "unmatched" ? "Not covered yet" : "All questions"}
              </button>
            ))}
          </div>
          {qaLogs.map((log) => (
            <div key={log.id} className="points-event-row" style={{ flexDirection: "column", alignItems: "flex-start", gap: 4 }}>
              <div style={{ fontWeight: 600 }}>{log.question}</div>
              <div className="hint">
                {log.user_email} · {new Date(log.created_at).toLocaleString()}
                {!log.matched_content && <span className="pill pill-pending" style={{ marginLeft: 8 }}>not covered</span>}
              </div>
            </div>
          ))}
          {qaLogs.length === 0 && <p className="muted">No questions yet.</p>}
        </div>
      )}

      {stats && (
        <div className="rise-hero">
          <div className="rise-stat">
            <div className="value">{stats.employees_joined}</div>
            <div className="label">Employees joined</div>
          </div>
          <div className="rise-stat">
            <div className="value">{stats.plans_generated}</div>
            <div className="label">Plans generated</div>
          </div>
          <div className="rise-stat">
            <div className="value">{stats.avg_messages_per_employee}</div>
            <div className="label">Avg. messages / employee</div>
          </div>
        </div>
      )}

      {analytics && (
        <div className="card">
          <div className="card-row">
            <h3 style={{ marginTop: 0 }}>Onboarding analytics</h3>
            <a
              href="#"
              className="btn btn-ghost btn-sm"
              onClick={(e) => {
                e.preventDefault();
                downloadFile(`/orgs/${org.id}/analytics/export.csv`, `riseply_org_${org.id}_analytics.csv`);
              }}
            >
              Download CSV report
            </a>
          </div>

          <p className="hint" style={{ marginTop: -4, marginBottom: 12 }}>
            Aggregate only — same principle as everywhere else in Org Buddy: this shows counts and
            rates, never which specific employee said or did what.
          </p>

          {analytics.avg_days_to_complete_onboarding !== null && (
            <p style={{ margin: "0 0 12px" }}>
              Employees who've finished onboarding took an average of{" "}
              <strong>{analytics.avg_days_to_complete_onboarding} days</strong> to complete every applicable checklist item.
            </p>
          )}

          {analytics.checklist_items.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <p style={{ fontWeight: 600, marginBottom: 6 }}>Checklist completion by item</p>
              {analytics.checklist_items.map((s) => (
                <div key={s.item_id} style={{ marginBottom: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.9rem" }}>
                    <span>{s.title}</span>
                    <span className="hint">{s.total_completed}/{s.total_assigned} · {s.completion_rate}%</span>
                  </div>
                  <div style={{ height: 6, background: "var(--paper)", borderRadius: 4, marginTop: 4, overflow: "hidden" }}>
                    <div style={{ width: `${s.completion_rate}%`, height: "100%", background: "var(--accent)" }} />
                  </div>
                </div>
              ))}
            </div>
          )}

          {analytics.lesson_quizzes.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <p style={{ fontWeight: 600, marginBottom: 6 }}>Culture Bot quiz performance</p>
              {analytics.lesson_quizzes.map((s) => (
                <div key={s.lesson_id} style={{ marginBottom: 6, fontSize: "0.9rem" }}>
                  <span>{s.title} — "{s.quiz_question}"</span>
                  <span className="hint" style={{ marginLeft: 8 }}>
                    {s.correct_count}/{s.total_attempts} correct · {s.correct_rate}%
                  </span>
                </div>
              ))}
            </div>
          )}

          {analytics.departments.length > 1 && (
            <div style={{ marginBottom: 16 }}>
              <p style={{ fontWeight: 600, marginBottom: 6 }}>By department</p>
              {analytics.departments.map((s) => (
                <div key={s.department_name} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.9rem", marginBottom: 4 }}>
                  <span>{s.department_name}</span>
                  <span className="hint">{s.completed_onboarding}/{s.total_employees} fully onboarded · {s.completion_rate}%</span>
                </div>
              ))}
            </div>
          )}

          {analytics.qa_gaps.length > 0 && (
            <div>
              <p style={{ fontWeight: 600, marginBottom: 6 }}>Most common content gaps</p>
              <p className="hint" style={{ marginTop: -4, marginBottom: 8 }}>
                Questions employees asked that nothing in your uploaded content actually answered —
                the clearest signal for what to add.
              </p>
              {analytics.qa_gaps.slice(0, 8).map((s) => (
                <div key={s.question} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.9rem", marginBottom: 4 }}>
                  <span>{s.question}</span>
                  <span className="hint">asked {s.count}×</span>
                </div>
              ))}
            </div>
          )}

          {analytics.mentorship.total_pairings > 0 && (
            <div>
              <p style={{ fontWeight: 600, marginBottom: 6 }}>Mentorship program</p>
              <div style={{ display: "flex", gap: 24, flexWrap: "wrap", fontSize: "0.9rem" }}>
                <div><strong>{analytics.mentorship.total_pairings}</strong> <span className="hint">pairings</span></div>
                <div><strong>{analytics.mentorship.employees_with_mentor_pct}%</strong> <span className="hint">of employees have a mentor</span></div>
                <div><strong>{analytics.mentorship.total_meetings_logged}</strong> <span className="hint">meetings logged</span></div>
                <div><strong>{analytics.mentorship.avg_meetings_per_pairing}</strong> <span className="hint">avg meetings/pairing</span></div>
                {analytics.mentorship.avg_feedback_rating !== null && (
                  <div><strong>{analytics.mentorship.avg_feedback_rating}/5</strong> <span className="hint">avg feedback rating</span></div>
                )}
              </div>
            </div>
          )}

          {analytics.total_employees === 0 && (
            <p className="muted">Nothing to show yet — analytics fill in once employees start joining and using the checklist/lessons.</p>
          )}
        </div>
      )}

      {billing && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Billing</h3>
          <p style={{ margin: 0 }}>
            Plan: <strong>{billing.plan === "none" ? "No plan yet" : billing.plan}</strong>
            {billing.plan !== "none" && <> — {billing.subscription_status}</>}
          </p>
          <p className="hint" style={{ marginTop: 4 }}>
            {billing.employees_joined} employee{billing.employees_joined === 1 ? "" : "s"} joined,
            {" "}{billing.included_seats} included in your plan.
            {billing.overage_seats > 0 && (
              <span style={{ color: "var(--danger)" }}>
                {" "}{billing.overage_seats} over your included seats (${billing.overage_cost_usd} — reconciled manually for now, not yet auto-billed).
              </span>
            )}
          </p>
          {billing.plan === "none" && !org.is_sandbox && (
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <button className="btn btn-primary btn-sm" onClick={() => subscribe("starter")}>
                Starter — $199/mo (10 seats)
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => subscribe("growth")}>
                Growth — $599/mo (50 seats)
              </button>
            </div>
          )}
          {org.is_sandbox && (
            <p className="hint" style={{ marginTop: 10 }}>Sandbox orgs can't be billed.</p>
          )}

          {!org.is_sandbox && (
            <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
              {enterpriseBillingSent ? (
                <p style={{ color: "var(--accent)", margin: 0 }}>{enterpriseBillingSent}</p>
              ) : !showEnterpriseBillingForm ? (
                <button className="btn btn-ghost btn-sm" onClick={() => setShowEnterpriseBillingForm(true)}>
                  Request enterprise billing (invoiced, NET-30)
                </button>
              ) : (
                <>
                  <p className="hint" style={{ marginTop: 0, marginBottom: 10 }}>
                    For larger teams that need invoicing instead of a card on file. We'll follow up
                    directly to set up the actual arrangement — this isn't automatic.
                  </p>
                  <div className="field">
                    <label>Billing contact name</label>
                    <input value={ebContactName} onChange={(e) => setEbContactName(e.target.value)} placeholder="Jane Finance" />
                  </div>
                  <div className="field">
                    <label>Billing contact email</label>
                    <input value={ebContactEmail} onChange={(e) => setEbContactEmail(e.target.value)} placeholder="jane@company.com" />
                  </div>
                  <div className="field">
                    <label>Estimated employees</label>
                    <input type="number" min={0} value={ebEmployeeCount} onChange={(e) => setEbEmployeeCount(e.target.value)} />
                  </div>
                  <div className="field">
                    <label>Notes (optional)</label>
                    <textarea rows={2} value={ebNotes} onChange={(e) => setEbNotes(e.target.value)} placeholder="Anything we should know — fiscal year timing, procurement process, etc." />
                  </div>
                  {ebError && <p className="error-text">{ebError}</p>}
                  <div style={{ display: "flex", gap: 8 }}>
                    <button className="btn btn-primary btn-sm" onClick={submitEnterpriseBilling}
                            disabled={ebSending || !ebContactName.trim() || !ebContactEmail.trim()}>
                      {ebSending ? "Sending…" : "Send request"}
                    </button>
                    <button className="btn btn-ghost btn-sm" onClick={() => setShowEnterpriseBillingForm(false)}>Cancel</button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {!org.is_sandbox && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Enterprise SSO</h3>
          <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
            Let employees sign in with your company's own identity provider — Okta, Azure AD,
            Google Workspace, or any other OIDC-compliant provider. Auto-provisions new employees
            with regular access only, same as joining with a code — SSO never grants admin rights.
          </p>

          {ssoConfig && !showSsoForm ? (
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <span className="pill pill-approved">Connected</span>
                <span style={{ fontWeight: 600 }}>{ssoConfig.provider_name || ssoConfig.issuer}</span>
              </div>
              <p className="hint" style={{ margin: "0 0 4px" }}>Issuer: {ssoConfig.issuer}</p>
              <p className="hint" style={{ margin: "0 0 10px" }}>Restricted to @{ssoConfig.allowed_email_domain} accounts</p>

              <div className="field">
                <label>Your SSO login link — share this with employees</label>
                <div style={{ display: "flex", gap: 8 }}>
                  <input readOnly value={`${API_URL}/auth/sso/${org.id}/login`} style={{ flex: 1 }} />
                  <button className="btn btn-ghost btn-sm" onClick={copySsoLink}>{ssoLinkCopied ? "Copied ✓" : "Copy"}</button>
                </div>
              </div>

              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button className="btn btn-ghost btn-sm" onClick={() => {
                  setShowSsoForm(true);
                  setSsoProviderName(ssoConfig.provider_name);
                  setSsoIssuer(ssoConfig.issuer);
                  setSsoClientId(ssoConfig.client_id);
                  setSsoClientSecret("");
                  setSsoDomain(ssoConfig.allowed_email_domain);
                }}>
                  Edit
                </button>
                <button className="btn btn-ghost btn-sm" onClick={removeSsoConfig}>Remove</button>
              </div>
            </div>
          ) : !showSsoForm ? (
            <button className="btn btn-ghost btn-sm" onClick={() => setShowSsoForm(true)}>Set up SSO</button>
          ) : (
            <>
              <div className="field">
                <label>Provider name (optional, for your own reference)</label>
                <input value={ssoProviderName} onChange={(e) => setSsoProviderName(e.target.value)} placeholder="e.g. Okta" />
              </div>
              <div className="field">
                <label>Issuer URL</label>
                <input value={ssoIssuer} onChange={(e) => setSsoIssuer(e.target.value)} placeholder="https://acme.okta.com" />
              </div>
              <div className="field">
                <label>Client ID</label>
                <input value={ssoClientId} onChange={(e) => setSsoClientId(e.target.value)} />
              </div>
              <div className="field">
                <label>Client secret</label>
                <input
                  type="password"
                  value={ssoClientSecret}
                  onChange={(e) => setSsoClientSecret(e.target.value)}
                  placeholder={ssoConfig ? "Enter a new secret to replace the existing one" : ""}
                />
              </div>
              <div className="field">
                <label>Allowed email domain</label>
                <input value={ssoDomain} onChange={(e) => setSsoDomain(e.target.value)} placeholder="acme.com" />
              </div>
              {ssoError && <p className="error-text">{ssoError}</p>}
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-primary btn-sm" onClick={saveSsoConfig}
                        disabled={ssoSaving || !ssoIssuer.trim() || !ssoClientId.trim() || !ssoClientSecret.trim() || !ssoDomain.trim()}>
                  {ssoSaving ? "Saving…" : "Save"}
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => setShowSsoForm(false)}>Cancel</button>
              </div>
            </>
          )}
        </div>
      )}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Employee roster</h3>
        <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
          Upload a CSV (columns: email, title, tenure, department, manager_email
          — all but email optional) to pre-register expected hires — they won't
          need to hand-type their title when they join. Export from Workday or
          any HRIS. Department names must match a department you've already
          created above. manager_email, if provided, gets a factual notification
          once that employee completes their onboarding checklist — never any
          conversation content.
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          style={{ display: "none" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadRoster(f); e.target.value = ""; }}
        />
        <button className="btn btn-ghost btn-sm" onClick={() => fileInputRef.current?.click()} disabled={rosterUploading}>
          {rosterUploading ? "Uploading…" : "Upload roster CSV"}
        </button>

        {rosterResult && (
          <p className="hint" style={{ marginTop: 8 }}>
            Added {rosterResult.added}, updated {rosterResult.updated}.
            {rosterResult.errors.length > 0 && ` ${rosterResult.errors.length} row(s) had issues: ${rosterResult.errors.join(" ")}`}
          </p>
        )}

        {roster.length > 0 && (
          <div style={{ marginTop: 16 }}>
            {roster.map((r) => (
              <div key={r.id} className="points-event-row">
                <div>
                  <div style={{ fontWeight: 600 }}>{r.email}</div>
                  <div className="hint">
                    {r.title || "(no title given)"}
                    {r.department_id && ` — ${departments.find((d) => d.id === r.department_id)?.name || "Department"}`}
                  </div>
                </div>
                <span className={`pill ${r.joined ? "pill-approved" : "pill-default"}`}>
                  {r.joined ? "Joined" : "Not yet joined"}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Human contacts</h3>
        <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
          Real people at your company for things AI can't do directly — an office
          tour, a face-to-face intro. Job Buddy will naturally mention them, and
          employees can request an actual handoff (a real email gets sent, containing
          only what the employee chooses to write — never their chat history).
        </p>

        {contacts.map((c) => (
          <div key={c.id} className="points-event-row">
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span className="avatar-initial avatar-initial-sm">{c.name.charAt(0).toUpperCase()}</span>
              <div>
                <div style={{ fontWeight: 600 }}>
                  {c.name} — {c.email}
                  {c.is_mentor && <span className="pill pill-approved" style={{ marginLeft: 8 }}>Mentor</span>}
                </div>
                <div className="hint">{c.description || "(no description)"}</div>
              </div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => removeContactEntry(c.id)}>Remove</button>
          </div>
        ))}

        <div style={{ marginTop: contacts.length > 0 ? 16 : 0 }}>
          <div className="field">
            <label>Name</label>
            <input value={contactName} onChange={(e) => setContactName(e.target.value)} placeholder="e.g. Sarah Chen" />
          </div>
          <div className="field">
            <label>Email</label>
            <input value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} placeholder="sarah@acme.com" />
          </div>
          <div className="field">
            <label>What they help with</label>
            <input value={contactDesc} onChange={(e) => setContactDesc(e.target.value)} placeholder="e.g. Office tours & facilities" />
          </div>
          <div className="field">
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 400 }}>
              <input type="checkbox" checked={contactIsMentor} onChange={(e) => setContactIsMentor(e.target.checked)} style={{ width: "auto" }} />
              Available as a mentor — can be assigned 1:1 to specific employees below
            </label>
          </div>
          {contactIsMentor && (
            <div className="field">
              <label>Mentor background</label>
              <textarea
                value={contactMentorBio}
                onChange={(e) => setContactMentorBio(e.target.value)}
                placeholder="e.g. 10 years in ICU nursing, previously mentored 3 new grads, strong at helping people navigate ambiguity"
                rows={3}
              />
              <p className="hint" style={{ marginTop: 4 }}>
                This is what AI-assisted mentor suggestions match against — the more specific, the better the suggestions.
              </p>
            </div>
          )}
          {departments.length > 0 && (
            <div className="field">
              <label>Scope</label>
              <select value={contactDept} onChange={(e) => setContactDept(e.target.value)}>
                <option value="">Company-wide (all employees)</option>
                {departments.map((d) => <option key={d.id} value={d.id}>{d.name} only</option>)}
              </select>
            </div>
          )}
          {contactError && <p className="error-text">{contactError}</p>}
          <button className="btn btn-primary btn-sm" onClick={addContact}
                  disabled={addingContact || !contactName.trim() || !contactEmail.trim()}>
            {addingContact ? "Adding…" : "Add contact"}

          </button>
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Mentor assignments</h3>
        <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
          Pair a specific employee with one mentor from the pool above. Assigned mentors show up
          on the employee's Job Buddy page with a direct "Request an intro" — not just left in
          the general contact list. Use "Suggest mentors (AI)" for a data-informed starting point
          based on the employee's resume and stated career goal — you still make the final call.
        </p>

        {employees.length === 0 ? (
          <p className="muted">No employees have joined yet.</p>
        ) : (
          employees.map((e) => {
            const mentorPool = contacts.filter((c) => c.is_mentor && (c.department_id === null || c.department_id === e.department_id));
            const ranked = suggestions[e.application_id];
            const employeeMeetings = e.mentor_assignment_id ? meetings[e.mentor_assignment_id] : undefined;
            return (
              <div key={e.application_id} style={{ marginBottom: 12, paddingBottom: 12, borderBottom: "1px solid var(--border, #eee)" }}>
                <div className="points-event-row" style={{ borderBottom: "none", paddingBottom: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span className="avatar-initial avatar-initial-sm">{e.user_full_name.charAt(0).toUpperCase()}</span>
                    <div>
                      <div style={{ fontWeight: 600 }}>{e.user_full_name}</div>
                      <div className="hint">
                        {e.user_email}{e.department_name && ` · ${e.department_name}`}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    {e.mentor_name && <span className="pill pill-approved">{e.mentor_name}</span>}
                    {mentorPool.length > 0 ? (
                      <>
                        <button className="btn btn-ghost btn-sm" onClick={() => loadSuggestedMentors(e.application_id)}>
                          {suggestingFor === e.application_id ? "Hide suggestions" : "Suggest mentors (AI)"}
                        </button>
                        <select
                          value=""
                          disabled={assigningEmployeeId === e.application_id}
                          onChange={(ev) => { if (ev.target.value) assignMentor(e.application_id, Number(ev.target.value)); }}
                          style={{ width: 180 }}
                        >
                          <option value="">{e.mentor_name ? "Reassign…" : "Assign a mentor…"}</option>
                          {mentorPool.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                        </select>
                      </>
                    ) : (
                      <span className="hint">No eligible mentors yet</span>
                    )}
                    {e.mentor_assignment_id && (
                      <button className="btn btn-ghost btn-sm" onClick={() => loadMeetings(e.mentor_assignment_id!)}>
                        {meetingLogOpenFor === e.mentor_assignment_id ? "Hide meetings" : "Meetings"}
                      </button>
                    )}
                  </div>
                </div>

                {suggestingFor === e.application_id && (
                  <div style={{ marginTop: 10, marginLeft: 42 }}>
                    {ranked === undefined ? (
                      <p className="hint">Scoring candidates…</p>
                    ) : ranked.length === 0 ? (
                      <p className="hint">No mentor scored well enough to suggest — try assigning manually from the list above.</p>
                    ) : (
                      ranked.map((s) => (
                        <div key={s.contact_id} className="points-event-row" style={{ padding: "8px 0" }}>
                          <div>
                            <div style={{ fontWeight: 600 }}>{s.name} <span className="pill" style={{ marginLeft: 6 }}>{s.score}% fit</span></div>
                            <div className="hint">{s.reason}</div>
                          </div>
                          <button
                            className="btn btn-primary btn-sm"
                            disabled={assigningEmployeeId === e.application_id}
                            onClick={() => assignMentor(e.application_id, s.contact_id)}
                          >
                            Assign
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                )}

                {e.mentor_assignment_id && meetingLogOpenFor === e.mentor_assignment_id && (
                  <div style={{ marginTop: 10, marginLeft: 42 }}>
                    {employeeMeetings === undefined ? (
                      <p className="hint">Loading meeting history…</p>
                    ) : employeeMeetings.length === 0 ? (
                      <p className="hint">No meetings logged yet.</p>
                    ) : (
                      <>
                        {employeeMeetings.map((m) => (
                          <div key={m.id} style={{ padding: "6px 0", borderBottom: "1px solid var(--border, #eee)" }}>
                            <div style={{ fontWeight: 600 }}>{m.meeting_date}{m.rating && ` · ${"★".repeat(m.rating)}${"☆".repeat(5 - m.rating)}`}</div>
                            {m.notes && <div className="hint">{m.notes}</div>}
                            {m.feedback_note && <div className="hint">Feedback: {m.feedback_note}</div>}
                          </div>
                        ))}
                        <button
                          className="btn btn-ghost btn-sm"
                          style={{ marginTop: 8 }}
                          onClick={() => downloadFile(
                            `/orgs/${org.id}/mentor-assignments/${e.mentor_assignment_id}/meetings/export`,
                            `mentorship_meetings_${e.mentor_assignment_id}.pdf`,
                          )}
                        >
                          Download PDF
                        </button>
                      </>
                    )}
                    <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "flex-end" }}>
                      <div className="field" style={{ marginBottom: 0 }}>
                        <label>Date</label>
                        <input type="date" value={newMeetingDate} onChange={(ev) => setNewMeetingDate(ev.target.value)} />
                      </div>
                      <div className="field" style={{ marginBottom: 0, flex: 1 }}>
                        <label>Notes (optional)</label>
                        <input value={newMeetingNotes} onChange={(ev) => setNewMeetingNotes(ev.target.value)} placeholder="What did you cover?" />
                      </div>
                      <button
                        className="btn btn-primary btn-sm"
                        disabled={loggingMeeting || !newMeetingDate}
                        onClick={() => logMeeting(e.mentor_assignment_id!)}
                      >
                        {loggingMeeting ? "Logging…" : "Log meeting"}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Custom onboarding content</h3>
        <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
          Handbook excerpts, culture notes, team/tool info — folded into every plan and chat reply for your employees.
        </p>

        {content.map((c) => (
          <div key={c.id} className="points-event-row" style={{ flexDirection: "column", alignItems: "stretch" }}>
            <div style={{ display: "flex", justifyContent: "space-between", width: "100%" }}>
              <div>
                <div style={{ fontWeight: 600 }}>
                  {c.title}
                  {c.department_id && (
                    <span className="hint" style={{ marginLeft: 8 }}>
                      ({departments.find((d) => d.id === c.department_id)?.name || "Department"})
                    </span>
                  )}
                </div>
                <div className="hint">{c.content.slice(0, 100)}{c.content.length > 100 ? "…" : ""}</div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => removeContent(c.id)}>Remove</button>
            </div>
            {c.media_url && <MediaEmbed url={c.media_url} />}
          </div>
        ))}

        <div style={{ marginTop: content.length > 0 ? 16 : 0 }}>
          <div className="field">
            <label>Title</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Engineering Handbook" />
          </div>
          <div className="field">
            <label>Content</label>
            <textarea rows={5} value={body} onChange={(e) => setBody(e.target.value)}
                      placeholder="Paste the relevant material here…" />
          </div>
          <div className="field">
            <label>Media link (optional)</label>
            <input value={contentMediaUrl} onChange={(e) => setContentMediaUrl(e.target.value)}
                   placeholder="https://youtube.com/watch?v=... or a link to a hosted image/document" />
            <p className="hint">
              YouTube, Vimeo, and Loom links embed as a video automatically. Image links (.jpg/.png/.gif/.webp)
              show inline. Anything else — a Drive doc, a PDF — shows as a link employees can open.
            </p>
          </div>
          {departments.length > 0 && (
            <div className="field">
              <label>Scope</label>
              <select value={contentDept} onChange={(e) => setContentDept(e.target.value)}>
                <option value="">Company-wide (all employees)</option>
                {departments.map((d) => <option key={d.id} value={d.id}>{d.name} only</option>)}
              </select>
            </div>
          )}
          {error && <p className="error-text">{error}</p>}
          <button className="btn btn-primary btn-sm" onClick={addContent} disabled={adding || !title.trim() || !body.trim()}>
            {adding ? "Adding…" : "Add content"}
          </button>
        </div>
      </div>
    </div>
  );
}
