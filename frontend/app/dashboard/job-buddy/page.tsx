"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
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
  const [apps, setApps] = useState<Application[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api<Application[]>("/applications?status=accepted").then((a) => {
      setApps(a);
      setLoaded(true);
    });
  }, []);

  return (
    <div>
      <h1>Job Buddy</h1>
      <p className="muted">
        Your onboarding mentor for a role you've accepted — a plan for your
        first weeks, and someone to ask "how do I handle this" as you settle in.
      </p>

      {loaded && apps.length === 0 && (
        <div className="empty-state">
          No accepted offers yet. Once you mark an application "Accepted" on
          the Applications page, it'll show up here.
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
      alert(err.message || "Couldn't generate your onboarding plan.");
    }
  }

  async function send() {
    if (!input.trim() || sending) return;
    const text = input;
    setInput("");
    setSending(true);
    // Optimistically show the user's message
    setMessages((m) => [...m, { id: -1, role: "user", content: text, created_at: new Date().toISOString() }]);
    try {
      await api(`/applications/${applicationId}/job-buddy/messages`, {
        method: "POST",
        body: JSON.stringify({ message: text }),
      });
      await loadMessages();
    } catch (err: any) {
      alert(err.message || "Job Buddy couldn't respond — try again.");
      await loadMessages(); // resync in case the user message was saved despite the error
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
        <Link href="/dashboard/applications" className="btn btn-ghost btn-sm">← Applications</Link>
      </div>

      {plan === "loading" && <p className="muted">Generating your onboarding plan…</p>}

      {plan === "none" && (
        <div className="card">
          <h3>No onboarding plan yet</h3>
          <p className="muted">Generate one first — Job Buddy uses it as context for the chat.</p>
          <button className="btn btn-primary btn-sm" onClick={generatePlan}>Generate onboarding plan</button>
        </div>
      )}

      {plan && plan !== "loading" && plan !== "none" && (
        <>
          <div className="card">
            <div className="card-row">
              <h3 style={{ margin: 0 }}>Your onboarding plan</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowPlan((s) => !s)}>
                {showPlan ? "Hide" : "Show"}
              </button>
            </div>
            {showPlan && <div className="brief">{plan.plan}</div>}
          </div>

          <div className="card">
            <h3>Chat with your Job Buddy</h3>
            <p className="hint" style={{ marginTop: -6, marginBottom: 12 }}>
              General career guidance only — not legal, medical, tax, or
              immigration advice. For harassment, discrimination, safety, or
              other serious workplace issues, please contact HR, an
              employment lawyer, or the relevant authority directly.
            </p>
            <div className="chat-window" ref={scrollRef}>
              {messages.length === 0 && (
                <p className="muted">
                  Ask anything about settling in — how to approach your first
                  week, handling a tricky conversation, prioritizing your
                  early projects, whatever's on your mind.
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
