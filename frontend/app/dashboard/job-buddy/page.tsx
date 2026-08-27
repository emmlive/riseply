"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, Application, OnboardingPlan, JobBuddyMessage, OrgContact, ChecklistProgressItem, LessonDelivery, OrgAskResponse, MentorAssignment, CareerGoal, MentorMeetingLog } from "@/lib/api";
import MediaEmbed from "@/components/MediaEmbed";

export default function JobBuddyPage() {
  return (
    <Suspense fallback={null}>
      <JobBuddyContent />
    </Suspense>
  );
}

function JobBuddyContent() {
  const params = useSearchParams();
  const applicationId = params.get("applicationId");

  if (!applicationId) {
    return <JobBuddyPicker />;
  }
  return <JobBuddyChat applicationId={Number(applicationId)} />;
}

function JobBuddyPicker() {
  const router = useRouter();
  const [apps, setApps] = useState<Application[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [tenure, setTenure] = useState<"just_started" | "a_few_months" | "well_established">("just_started");
  const [description, setDescription] = useState("");
  const [orgJoinCode, setOrgJoinCode] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  function load() {
    api<Application[]>("/applications?status=accepted").then((a) => {
      setApps(a);
      setLoaded(true);
    });
  }

  useEffect(() => { load(); }, []);

  async function addCurrentJob() {
    setAdding(true);
    setError("");
    try {
      const app = await api<Application>("/applications/current-job", {
        method: "POST",
        body: JSON.stringify({ company, title, tenure, description, org_join_code: orgJoinCode }),
      });
      router.push(`/dashboard/job-buddy?applicationId=${app.id}`);
    } catch (err: any) {
      setError(err.message || "Couldn't add that job.");
      setAdding(false);
    }
  }

  return (
    <div>
      <h1>Job Buddy</h1>
      <p className="muted">
        Your ongoing work mentor — whether you just landed a role through
        Riseply, or you already have a job and want support for what comes
        next. A plan tailored to where you actually are, and someone to ask
        "how do I handle this" as things come up.
      </p>

      {!showAddForm ? (
        <button className="btn btn-primary btn-sm" onClick={() => setShowAddForm(true)}>
          + Add a job you already have
        </button>
      ) : (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Add your current job</h3>
          <p className="hint" style={{ marginTop: -6 }}>
            Doesn't need to have come through Riseply — this just unlocks Job Buddy for it.
          </p>
          <div className="field">
            <label>Company</label>
            <input value={company} onChange={(e) => setCompany(e.target.value)} />
          </div>
          <div className="field">
            <label>Job title</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="field">
            <label>How long have you been there?</label>
            <select value={tenure} onChange={(e) => setTenure(e.target.value as typeof tenure)}>
              <option value="just_started">Just started / about to start</option>
              <option value="a_few_months">A few months in</option>
              <option value="well_established">Well established</option>
            </select>
          </div>
          <div className="field">
            <label>What do you do there? (optional, helps Job Buddy give better advice)</label>
            <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)}
                      placeholder="Brief description of your role and responsibilities…" />
          </div>
          <div className="field">
            <label>Organization join code (optional)</label>
            <input value={orgJoinCode} onChange={(e) => setOrgJoinCode(e.target.value)}
                   placeholder="If your employer set up Org Buddy, enter it here" />
            <p className="hint">Links your plan to your company's own onboarding materials, if they've set this up.</p>
          </div>
          {error && <p className="error-text">{error}</p>}
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary btn-sm" onClick={addCurrentJob}
                    disabled={adding || !company.trim() || !title.trim()}>
              {adding ? "Adding…" : "Add & open Job Buddy"}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => setShowAddForm(false)}>Cancel</button>
          </div>
        </div>
      )}

      {loaded && apps.length === 0 && !showAddForm && (
        <div className="empty-state">
          No accepted offers yet. Mark an application "Accepted" on the
          Applications page, or add a job you already have above.
        </div>
      )}

      {apps.map((app) => (
        <div key={app.id} className="card">
          <div className="card-row">
            <div>
              <h3>{app.job_title} — {app.job_company}</h3>
              <p className="muted" style={{ margin: 0 }}>{app.job_location}</p>
            </div>
            <Link href={`/dashboard/job-buddy?applicationId=${app.id}`} className="btn btn-primary btn-sm">
              Open →
            </Link>
          </div>
        </div>
      ))}
    </div>
  );
}

function JobBuddyChat({ applicationId }: { applicationId: number }) {
  const [app, setApp] = useState<Application | null>(null);
  const [plan, setPlan] = useState<OnboardingPlan | "loading" | "none" | null>(null);
  const [messages, setMessages] = useState<JobBuddyMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [showPlan, setShowPlan] = useState(false);
  const [handoffContacts, setHandoffContacts] = useState<OrgContact[]>([]);
  const [showHandoffForm, setShowHandoffForm] = useState(false);
  const [handoffContactId, setHandoffContactId] = useState<number | null>(null);
  const [handoffNote, setHandoffNote] = useState("");
  const [handoffSending, setHandoffSending] = useState(false);
  const [handoffSent, setHandoffSent] = useState("");
  const [checklist, setChecklist] = useState<ChecklistProgressItem[]>([]);
  const [expandedPolicyId, setExpandedPolicyId] = useState<number | null>(null);
  const [lessons, setLessons] = useState<LessonDelivery[]>([]);
  const [quizDrafts, setQuizDrafts] = useState<Record<number, string>>({});
  const [quizSubmittingId, setQuizSubmittingId] = useState<number | null>(null);
  const [askQuestion, setAskQuestion] = useState("");
  const [askAnswer, setAskAnswer] = useState<OrgAskResponse | null>(null);
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState("");
  const [mentor, setMentor] = useState<MentorAssignment | null>(null);
  const [mentorMeetings, setMentorMeetings] = useState<MentorMeetingLog[]>([]);
  const [showMentorMeetings, setShowMentorMeetings] = useState(false);
  const [newMeetingDate, setNewMeetingDate] = useState("");
  const [newMeetingNotes, setNewMeetingNotes] = useState("");
  const [loggingMeeting, setLoggingMeeting] = useState(false);
  const [feedbackDraftFor, setFeedbackDraftFor] = useState<number | null>(null);
  const [feedbackRating, setFeedbackRating] = useState(5);
  const [feedbackNote, setFeedbackNote] = useState("");
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [goals, setGoals] = useState<CareerGoal[]>([]);
  const [newGoal, setNewGoal] = useState("");
  const [addingGoal, setAddingGoal] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<Application>(`/applications/${applicationId}`).then(setApp);
    api<OrgContact[]>(`/applications/${applicationId}/handoff-contacts`).then(setHandoffContacts).catch(() => {});
    api<ChecklistProgressItem[]>(`/applications/${applicationId}/checklist`).then(setChecklist).catch(() => {});
    api<LessonDelivery[]>(`/applications/${applicationId}/lessons`).then(setLessons).catch(() => {});
    api<MentorAssignment | null>(`/applications/${applicationId}/mentor`).then(setMentor).catch(() => {});
    api<CareerGoal[]>(`/applications/${applicationId}/career-goals`).then(setGoals).catch(() => {});

    api<OnboardingPlan>(`/applications/${applicationId}/onboarding-plan`)
      .then((p) => {
        setPlan(p);
        loadMessages();
      })
      .catch(() => setPlan("none"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applicationId]);

  async function loadMessages() {
    const msgs = await api<JobBuddyMessage[]>(`/applications/${applicationId}/job-buddy/messages`);
    setMessages(msgs);
  }

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function generatePlan() {
    setPlan("loading");
    try {
      const p = await api<OnboardingPlan>(`/applications/${applicationId}/onboarding-plan`, { method: "POST" });
      setPlan(p);
    } catch (err: any) {
      setPlan("none");
      alert(err.message || "Couldn't generate your plan.");
    }
  }

  async function send() {
    if (!input.trim() || sending) return;
    const text = input;
    setInput("");
    setSending(true);
    setMessages((m) => [...m, { id: -1, role: "user", content: text, created_at: new Date().toISOString() }]);
    try {
      await api(`/applications/${applicationId}/job-buddy/messages`, {
        method: "POST",
        body: JSON.stringify({ message: text }),
      });
      await loadMessages();
    } catch (err: any) {
      alert(err.message || "Job Buddy couldn't respond — try again.");
      await loadMessages();
    } finally {
      setSending(false);
    }
  }

  async function sendHandoff() {
    if (!handoffContactId || !handoffNote.trim()) return;
    setHandoffSending(true);
    try {
      const result = await api<{ sent: boolean; contact_name: string }>(
        `/applications/${applicationId}/handoff`,
        { method: "POST", body: JSON.stringify({ contact_id: handoffContactId, note: handoffNote }) }
      );
      setHandoffSent(`Sent to ${result.contact_name}.`);
      setHandoffNote("");
      setShowHandoffForm(false);
    } catch (err: any) {
      alert(err.message || "Couldn't send that — try again.");
    } finally {
      setHandoffSending(false);
    }
  }

  function openHandoffToMentor() {
    if (!mentor) return;
    setHandoffContactId(mentor.contact_id);
    setShowHandoffForm(true);
  }

  async function toggleMentorMeetings() {
    if (!mentor || !app?.organization_id) return;
    if (showMentorMeetings) {
      setShowMentorMeetings(false);
      return;
    }
    setShowMentorMeetings(true);
    try {
      const rows = await api<MentorMeetingLog[]>(`/orgs/${app.organization_id}/mentor-assignments/${mentor.id}/meetings`);
      setMentorMeetings(rows);
    } catch {
      // quietly leave the list empty rather than blocking the rest of the page
    }
  }

  async function logMentorMeeting() {
    if (!mentor || !app?.organization_id || !newMeetingDate) return;
    setLoggingMeeting(true);
    try {
      await api(`/orgs/${app.organization_id}/mentor-assignments/${mentor.id}/meetings`, {
        method: "POST",
        body: JSON.stringify({ meeting_date: newMeetingDate, notes: newMeetingNotes }),
      });
      setNewMeetingDate(""); setNewMeetingNotes("");
      const rows = await api<MentorMeetingLog[]>(`/orgs/${app.organization_id}/mentor-assignments/${mentor.id}/meetings`);
      setMentorMeetings(rows);
    } catch (err: any) {
      alert(err.message || "Couldn't log that meeting.");
    } finally {
      setLoggingMeeting(false);
    }
  }

  function openFeedbackDraft(meetingId: number) {
    setFeedbackDraftFor(meetingId);
    setFeedbackRating(5);
    setFeedbackNote("");
  }

  async function submitMeetingFeedback(meetingId: number) {
    if (!app?.organization_id) return;
    setSubmittingFeedback(true);
    try {
      await api(`/orgs/${app.organization_id}/mentor-meetings/${meetingId}/feedback`, {
        method: "POST",
        body: JSON.stringify({ rating: feedbackRating, feedback_note: feedbackNote }),
      });
      setFeedbackDraftFor(null);
      if (mentor) {
        const rows = await api<MentorMeetingLog[]>(`/orgs/${app.organization_id}/mentor-assignments/${mentor.id}/meetings`);
        setMentorMeetings(rows);
      }
    } catch (err: any) {
      alert(err.message || "Couldn't submit feedback.");
    } finally {
      setSubmittingFeedback(false);
    }
  }

  async function addGoal() {
    if (!newGoal.trim()) return;
    setAddingGoal(true);
    try {
      const goal = await api<CareerGoal>(`/applications/${applicationId}/career-goals`, {
        method: "POST", body: JSON.stringify({ goal_text: newGoal.trim() }),
      });
      setGoals((prev) => [goal, ...prev]);
      setNewGoal("");
    } catch (err: any) {
      alert(err.message || "Couldn't add that goal.");
    } finally {
      setAddingGoal(false);
    }
  }

  async function toggleGoalAchieved(goal: CareerGoal) {
    try {
      if (goal.achieved_at) {
        // No "un-achieve" endpoint exists -- achieving is a one-way
        // milestone, same as checking off an onboarding checklist item.
        return;
      }
      const updated = await api<CareerGoal>(`/applications/${applicationId}/career-goals/${goal.id}/achieve`, { method: "POST" });
      setGoals((prev) => prev.map((g) => (g.id === updated.id ? updated : g)));
    } catch (err: any) {
      alert(err.message || "Couldn't update that goal.");
    }
  }

  async function removeGoal(goalId: number) {
    try {
      await api(`/applications/${applicationId}/career-goals/${goalId}`, { method: "DELETE" });
      setGoals((prev) => prev.filter((g) => g.id !== goalId));
    } catch (err: any) {
      alert(err.message || "Couldn't remove that goal.");
    }
  }

  async function completeChecklistItem(itemId: number) {
    setChecklist((items) => items.map((i) => (i.id === itemId ? { ...i, completed: true } : i)));
    try {
      await api(`/applications/${applicationId}/checklist/${itemId}/complete`, { method: "POST" });
    } catch (err: any) {
      setChecklist((items) => items.map((i) => (i.id === itemId ? { ...i, completed: false } : i)));
      alert(err.message || "Couldn't save that — try again.");
    }
  }

  async function submitQuizResponse(deliveryId: number) {
    const response = quizDrafts[deliveryId];
    if (!response?.trim()) return;
    setQuizSubmittingId(deliveryId);
    try {
      const result = await api<{ correct: boolean }>(
        `/applications/${applicationId}/lessons/${deliveryId}/quiz-response`,
        { method: "POST", body: JSON.stringify({ response }) }
      );
      setLessons((ls) => ls.map((l) => (l.id === deliveryId ? { ...l, quiz_response: response, quiz_correct: result.correct } : l)));
    } catch (err: any) {
      alert(err.message || "Couldn't save that answer — try again.");
    } finally {
      setQuizSubmittingId(null);
    }
  }

  async function askOrgQuestion() {
    if (!askQuestion.trim() || asking) return;
    setAsking(true);
    setAskError("");
    setAskAnswer(null);
    try {
      const result = await api<OrgAskResponse>(`/applications/${applicationId}/org-ask`, {
        method: "POST", body: JSON.stringify({ question: askQuestion }),
      });
      setAskAnswer(result);
    } catch (err: any) {
      setAskError(err.message || "Couldn't get an answer — try again.");
    } finally {
      setAsking(false);
    }
  }

  if (plan === null) return <p className="muted">Loading…</p>;

  return (
    <div>
      <div className="topbar">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {app?.organization_logo_url && (
            <img src={app.organization_logo_url} alt="" style={{ width: 32, height: 32, objectFit: "contain", borderRadius: 6 }}
                 onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
          )}
          <div>
            <h1>Job Buddy</h1>
            {app && <p className="muted" style={{ marginTop: -12 }}>{app.job_title} — {app.job_company}</p>}
          </div>
        </div>
        <Link href="/dashboard/job-buddy" className="btn btn-ghost btn-sm">← Job Buddy</Link>
      </div>

      {plan === "loading" && <p className="muted">Generating your plan…</p>}

      {plan === "none" && (
        <div className="card">
          <h3>No plan yet</h3>
          <p className="muted">Generate one first — Job Buddy uses it as context for the chat.</p>
          <button className="btn btn-primary btn-sm" onClick={generatePlan}>Generate my plan</button>
        </div>
      )}

      {plan && plan !== "loading" && plan !== "none" && (
        <>
          <div className="card">
            <div className="card-row">
              <h3 style={{ margin: 0 }}>Your plan</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowPlan((s) => !s)}>
                {showPlan ? "Hide" : "Show"}
              </button>
            </div>
            {showPlan && <div className="brief">{plan.plan}</div>}
          </div>

          {checklist.length > 0 && (
            <div className="card">
              <h3 style={{ marginTop: 0 }}>Onboarding checklist</h3>
              <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
                {checklist.filter((c) => c.completed).length} of {checklist.length} done
              </p>
              {checklist.map((c) => (
                <div key={c.id} style={{ padding: "8px 0" }}>
                  {c.policy_content ? (
                    <div>
                      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                        <span style={{ marginTop: 3 }}>{c.completed ? "✅" : "📄"}</span>
                        <div style={{ flex: 1 }}>
                          <div style={{ textDecoration: c.completed ? "line-through" : "none", color: c.completed ? "var(--muted)" : "inherit", fontWeight: 600 }}>
                            {c.title}
                          </div>
                          {!c.completed && (
                            <>
                              <button className="btn btn-ghost btn-sm" style={{ marginTop: 6 }}
                                      onClick={() => setExpandedPolicyId(expandedPolicyId === c.id ? null : c.id)}>
                                {expandedPolicyId === c.id ? "Hide" : "Read policy"}
                              </button>
                              {expandedPolicyId === c.id && (
                                <div>
                                  <div className="brief" style={{ marginTop: 8 }}>{c.policy_content}</div>
                                  {c.media_url && <MediaEmbed url={c.media_url} />}
                                  <button className="btn btn-primary btn-sm" style={{ marginTop: 8 }}
                                          onClick={() => completeChecklistItem(c.id)}>
                                    I have read and acknowledge this
                                  </button>
                                </div>
                              )}
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <label style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                      <input
                        type="checkbox"
                        checked={c.completed}
                        disabled={c.completed}
                        onChange={() => completeChecklistItem(c.id)}
                        style={{ marginTop: 3 }}
                      />
                      <span style={{ textDecoration: c.completed ? "line-through" : "none", color: c.completed ? "var(--muted)" : "inherit", flex: 1 }}>
                        {c.title}
                        {c.description && <div className="hint" style={{ textDecoration: "none" }}>{c.description}</div>}
                        {c.media_url && <div style={{ textDecoration: "none" }}><MediaEmbed url={c.media_url} /></div>}
                      </span>
                    </label>
                  )}
                </div>
              ))}
            </div>
          )}

          {lessons.length > 0 && (
            <div className="card">
              <h3 style={{ marginTop: 0 }}>Lessons</h3>
              <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
                Short check-ins from {app?.job_company || "your company"}, delivered a few at a time
                instead of all at once.
              </p>
              {lessons.map((l) => (
                <div key={l.id} style={{ padding: "10px 0", borderTop: "1px solid var(--border)" }}>
                  <div style={{ fontWeight: 600 }}>{l.title}</div>
                  <div className="hint" style={{ margin: "4px 0" }}>{l.content}</div>
                  {l.media_url && <MediaEmbed url={l.media_url} />}
                  {l.quiz_question && (
                    <div style={{ marginTop: 8 }}>
                      {l.quiz_correct === true && (
                        <p style={{ color: "var(--accent)", margin: 0 }}>✅ {l.quiz_question} — got it.</p>
                      )}
                      {l.quiz_correct === false && (
                        <p style={{ color: "var(--danger)", margin: 0 }}>
                          {l.quiz_question} — not quite: "{l.quiz_response}". You'll get a reminder in a week.
                        </p>
                      )}
                      {l.quiz_correct == null && (
                        <div style={{ display: "flex", gap: 8 }}>
                          <input
                            value={quizDrafts[l.id] || ""}
                            onChange={(e) => setQuizDrafts({ ...quizDrafts, [l.id]: e.target.value })}
                            placeholder={l.quiz_question}
                            style={{ flex: 1 }}
                          />
                          <button
                            className="btn btn-ghost btn-sm"
                            disabled={quizSubmittingId === l.id || !(quizDrafts[l.id] || "").trim()}
                            onClick={() => submitQuizResponse(l.id)}
                          >
                            {quizSubmittingId === l.id ? "Checking…" : "Answer"}
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {app?.organization_id && (
            <div className="card">
              <h3 style={{ marginTop: 0 }}>Ask about {app.job_company || "your company"}</h3>
              <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
                Quick factual lookups — where to request PTO, who to ask about something —
                answered instantly from your company's own materials, not a chat conversation.
              </p>
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  value={askQuestion}
                  onChange={(e) => setAskQuestion(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && askOrgQuestion()}
                  placeholder="e.g. How do I request time off?"
                  style={{ flex: 1 }}
                />
                <button className="btn btn-primary btn-sm" onClick={askOrgQuestion} disabled={asking || !askQuestion.trim()}>
                  {asking ? "Asking…" : "Ask"}
                </button>
              </div>
              {askError && <p className="error-text">{askError}</p>}
              {askAnswer && (
                <div className="brief" style={{ marginTop: 12 }}>
                  {askAnswer.answer}
                  {askAnswer.sources.length > 0 && (
                    <p className="hint" style={{ marginTop: 8, marginBottom: 0 }}>
                      From: {askAnswer.sources.join(", ")}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {mentor && (
            <div className="card" style={{ borderColor: "var(--accent)", background: "linear-gradient(180deg, var(--accent-soft) 0%, var(--surface) 120px)" }}>
              <p className="hint" style={{ margin: "0 0 10px", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600, color: "var(--accent-hover)" }}>
                Your Mentor
              </p>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span className="avatar-initial">{mentor.name.charAt(0).toUpperCase()}</span>
                <div>
                  <div style={{ fontWeight: 600, fontFamily: "var(--font-display)", fontSize: "1.05rem" }}>{mentor.name}</div>
                  {mentor.description && <div className="hint" style={{ marginTop: 1 }}>{mentor.description}</div>}
                </div>
              </div>
              <p className="hint" style={{ marginTop: 12, marginBottom: 10 }}>
                Assigned to help you specifically, beyond what Job Buddy can do directly.
              </p>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-primary btn-sm" onClick={openHandoffToMentor}>Request an intro</button>
                <button className="btn btn-ghost btn-sm" onClick={toggleMentorMeetings}>
                  {showMentorMeetings ? "Hide meetings" : "Log a meeting"}
                </button>
              </div>

              {showMentorMeetings && (
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border, #eee)" }}>
                  {mentorMeetings.length === 0 ? (
                    <p className="hint" style={{ marginTop: 0 }}>No meetings logged yet.</p>
                  ) : (
                    mentorMeetings.map((m) => (
                      <div key={m.id} style={{ marginBottom: 10, fontSize: "0.9rem" }}>
                        <div style={{ fontWeight: 600 }}>{m.meeting_date}</div>
                        {m.notes && <div className="hint">{m.notes}</div>}
                        {m.rating ? (
                          <div className="hint">Your rating: {"★".repeat(m.rating)}{"☆".repeat(5 - m.rating)}</div>
                        ) : feedbackDraftFor === m.id ? (
                          <div style={{ marginTop: 6 }}>
                            <div className="field" style={{ marginBottom: 6 }}>
                              <label>How'd it go? (1-5)</label>
                              <select value={feedbackRating} onChange={(e) => setFeedbackRating(Number(e.target.value))}>
                                {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
                              </select>
                            </div>
                            <div className="field" style={{ marginBottom: 6 }}>
                              <label>Notes (optional)</label>
                              <input value={feedbackNote} onChange={(e) => setFeedbackNote(e.target.value)} placeholder="Anything you'd want to remember" />
                            </div>
                            <button className="btn btn-primary btn-sm" disabled={submittingFeedback} onClick={() => submitMeetingFeedback(m.id)}>
                              {submittingFeedback ? "Saving…" : "Submit feedback"}
                            </button>
                          </div>
                        ) : (
                          <button className="btn btn-ghost btn-sm" onClick={() => openFeedbackDraft(m.id)} style={{ padding: "2px 8px", fontSize: "0.85rem" }}>
                            Rate this meeting
                          </button>
                        )}
                      </div>
                    ))
                  )}
                  <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "flex-end" }}>
                    <div className="field" style={{ marginBottom: 0 }}>
                      <label>Date</label>
                      <input type="date" value={newMeetingDate} onChange={(e) => setNewMeetingDate(e.target.value)} />
                    </div>
                    <div className="field" style={{ marginBottom: 0, flex: 1 }}>
                      <label>Notes (optional)</label>
                      <input value={newMeetingNotes} onChange={(e) => setNewMeetingNotes(e.target.value)} placeholder="What did you cover?" />
                    </div>
                    <button className="btn btn-primary btn-sm" disabled={loggingMeeting || !newMeetingDate} onClick={logMentorMeeting}>
                      {loggingMeeting ? "Logging…" : "Log"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="card">
            <h3 style={{ marginTop: 0 }}>Career goals</h3>
            <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
              Job Buddy keeps these in mind across your conversations, the way a real mentor
              remembers what you're working toward instead of starting fresh every time.
            </p>

            {goals.length === 0 ? (
              <p className="muted" style={{ marginBottom: 12 }}>
                No goals set yet — add one below and Job Buddy will factor it into its advice.
              </p>
            ) : (
              <div style={{ marginBottom: 12 }}>
                {goals.map((goal) => (
                  <div key={goal.id} style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "6px 0" }}>
                    <input
                      type="checkbox"
                      checked={!!goal.achieved_at}
                      disabled={!!goal.achieved_at}
                      onChange={() => toggleGoalAchieved(goal)}
                      style={{ marginTop: 3 }}
                      title={goal.achieved_at ? "Achieved" : "Mark as achieved"}
                    />
                    <span style={{
                      flex: 1, textDecoration: goal.achieved_at ? "line-through" : "none",
                      color: goal.achieved_at ? "var(--ink-muted)" : "inherit",
                    }}>
                      {goal.goal_text}
                    </span>
                    <button
                      className="btn btn-ghost btn-sm"
                      style={{ padding: "2px 8px" }}
                      onClick={() => removeGoal(goal.id)}
                      title="Remove"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div style={{ display: "flex", gap: 8 }}>
              <input
                value={newGoal}
                onChange={(e) => setNewGoal(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") addGoal(); }}
                placeholder="e.g. Get better at public speaking"
                style={{ flex: 1 }}
              />
              <button className="btn btn-primary btn-sm" onClick={addGoal} disabled={addingGoal || !newGoal.trim()}>
                {addingGoal ? "Adding…" : "Add"}
              </button>
            </div>
          </div>

          {handoffContacts.length > 0 && (
            <div className="card">
              <h3 style={{ marginTop: 0 }}>Need an actual person?</h3>
              <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
                For things Job Buddy can't do directly — a tour, a face-to-face intro —
                you can request a real handoff. Only your own note gets sent, never this chat.
              </p>
              {handoffSent && <p style={{ color: "var(--accent)" }}>{handoffSent}</p>}
              {!showHandoffForm ? (
                <button className="btn btn-ghost btn-sm" onClick={() => setShowHandoffForm(true)}>
                  Request a handoff
                </button>
              ) : (
                <>
                  <div className="field">
                    <label>Who</label>
                    <select value={handoffContactId ?? ""} onChange={(e) => setHandoffContactId(Number(e.target.value))}>
                      <option value="" disabled>Choose someone…</option>
                      {handoffContacts.map((c) => (
                        <option key={c.id} value={c.id}>{c.name} — {c.description}</option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label>Your note</label>
                    <textarea rows={3} value={handoffNote} onChange={(e) => setHandoffNote(e.target.value)}
                              placeholder="What would you like their help with?" />
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button className="btn btn-primary btn-sm" onClick={sendHandoff}
                            disabled={handoffSending || !handoffContactId || !handoffNote.trim()}>
                      {handoffSending ? "Sending…" : "Send"}
                    </button>
                    <button className="btn btn-ghost btn-sm" onClick={() => setShowHandoffForm(false)}>Cancel</button>
                  </div>
                </>
              )}
            </div>
          )}

          <div className="card">
            <h3>Chat with your Job Buddy</h3>
            <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
              General career and day-to-day work guidance only — not legal, medical, tax, or
              immigration advice. For harassment, discrimination, safety, or
              other serious workplace issues, please contact HR, an
              employment lawyer, or the relevant authority directly.
            </p>
            <div className="chat-window" ref={scrollRef}>
              {messages.length === 0 && (
                <p className="muted">
                  Ask anything about this role — settling in, a tricky
                  conversation, prioritizing your work, asking for more
                  scope or a raise, whatever's on your mind.
                </p>
              )}
              {messages.map((m) => (
                <div key={m.id} className={`chat-bubble ${m.role}`}>{m.content}</div>
              ))}
              {sending && <div className="chat-bubble assistant muted">Thinking…</div>}
            </div>
            <div className="chat-input-row">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                placeholder="Ask your Job Buddy something…"
              />
              <button className="btn btn-primary" onClick={send} disabled={sending || !input.trim()}>
                Send
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
