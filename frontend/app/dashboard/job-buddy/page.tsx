"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, Application, OnboardingPlan, JobBuddyMessage } from "@/lib/api";

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
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<Application>(`/applications/${applicationId}`).then(setApp);

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

  if (plan === null) return <p className="muted">Loading…</p>;

  return (
    <div>
      <div className="topbar">
        <div>
          <h1>Job Buddy</h1>
          {app && <p className="muted" style={{ marginTop: -12 }}>{app.job_title} — {app.job_company}</p>}
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
