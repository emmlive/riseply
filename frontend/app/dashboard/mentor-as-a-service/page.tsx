"use client";

import { useEffect, useState } from "react";
import {
  api, downloadFile, Organization, OrgEmployee, OrgContact, SuggestedMentor,
  MentorMeetingLog, MentorMeetingSchedule, MentorshipRelationship, MEETING_AGENDA_TEMPLATES,
} from "@/lib/api";

// This page used to be two cards ("Mentor assignments" and "Group &
// reciprocal mentoring") living inside Org Buddy's admin page. Pulled out
// into its own dedicated page + sidebar nav entry to give it real, equal
// billing alongside Org Buddy -- matching how the two are positioned
// externally (riseply.com/mentor-as-a-service: "the growth half of the
// same platform as Buddy as a Service"). Genuinely moved, not duplicated
// -- keeping mentor-assignment logic in two places would mean keeping two
// copies of the same forms in sync every time either changes.
//
// Adding a new mentor to the pool (the org's contact directory, with the
// "Available as a mentor" checkbox + bio field) still happens in Org
// Buddy's contact management -- a mentor is fundamentally a flagged
// OrgHumanContact, and contacts as a concept (general handoff contacts
// like IT/facilities, alongside mentors) reasonably stay together in one
// place. This page assigns FROM that existing pool; it doesn't duplicate
// creating it.

export default function MentorAsAServicePage() {
  const [orgs, setOrgs] = useState<Organization[] | null>(null);
  const [selected, setSelected] = useState<Organization | null>(null);

  useEffect(() => {
    api<Organization[]>("/orgs/mine").then((orgList) => {
      setOrgs(orgList);
      if (orgList.length > 0 && !selected) setSelected(orgList[0]);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (orgs === null) return <p className="muted">Loading…</p>;

  if (orgs.length === 0) {
    return (
      <div>
        <h1>Mentor as a Service</h1>
        <p className="muted">
          You'll need an organization set up first — head to Org Buddy to create one, then come
          back here to build out mentor pairings and groups.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="topbar">
        <h1>Mentor as a Service</h1>
        {orgs.length > 1 && (
          <select
            value={selected?.id ?? ""}
            onChange={(e) => setSelected(orgs.find((o) => o.id === Number(e.target.value)) || null)}
            style={{ width: 220 }}
          >
            {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        )}
      </div>
      <p className="muted">
        The growth half of the same platform as Org Buddy — where Org Buddy gets someone through
        their first weeks, this keeps them growing after that. A real internal mentor, matched
        1:1, or a group cohort, or a reciprocal peer pair, plus meeting logs, scheduling with a
        real calendar invite, and end-of-pairing retrospectives.
      </p>
      {selected && <MentorshipDashboard org={selected} />}
    </div>
  );
}

function MentorshipDashboard({ org }: { org: Organization }) {
  const [employees, setEmployees] = useState<OrgEmployee[]>([]);
  const [contacts, setContacts] = useState<OrgContact[]>([]);

  const [assigningEmployeeId, setAssigningEmployeeId] = useState<number | null>(null);
  const [suggestingFor, setSuggestingFor] = useState<number | null>(null);
  const [suggestions, setSuggestions] = useState<Record<number, SuggestedMentor[]>>({});
  const [meetingLogOpenFor, setMeetingLogOpenFor] = useState<number | null>(null);
  const [meetings, setMeetings] = useState<Record<number, MentorMeetingLog[]>>({});
  const [newMeetingDate, setNewMeetingDate] = useState("");
  const [newMeetingNotes, setNewMeetingNotes] = useState("");
  const [loggingMeeting, setLoggingMeeting] = useState(false);
  const [endingPairingId, setEndingPairingId] = useState<number | null>(null);
  const [scheduleOpenFor, setScheduleOpenFor] = useState<number | null>(null);
  const [schedules, setSchedules] = useState<Record<number, MentorMeetingSchedule[]>>({});
  const [newScheduleAt, setNewScheduleAt] = useState("");
  const [newScheduleDuration, setNewScheduleDuration] = useState(30);
  const [schedulingMeeting, setSchedulingMeeting] = useState(false);
  const [relationships, setRelationships] = useState<MentorshipRelationship[]>([]);
  const [newRelationshipType, setNewRelationshipType] = useState<string | null>(null);
  const [newRelationshipName, setNewRelationshipName] = useState("");
  const [newRelationshipParticipants, setNewRelationshipParticipants] = useState<{ application_id: number; role: string }[]>([]);
  const [creatingRelationship, setCreatingRelationship] = useState(false);

  function load() {
    api<OrgContact[]>(`/orgs/${org.id}/contacts`).then(setContacts).catch(() => {});
    api<OrgEmployee[]>(`/orgs/${org.id}/employees`).then(setEmployees).catch(() => {});
  }

  useEffect(() => { load(); loadRelationships(); }, [org.id]);

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

  async function endPairing(assignmentId: number) {
    const reason = prompt("Why is this pairing ending? (e.g. Completed, Reassigning, Employee departed) — optional");
    if (reason === null) return;  // user cancelled
    setEndingPairingId(assignmentId);
    try {
      await api(`/orgs/${org.id}/mentor-assignments/${assignmentId}/end`, {
        method: "POST", body: JSON.stringify({ reason }),
      });
      load();
    } catch (err: any) {
      alert(err.message || "Couldn't end that pairing.");
    } finally {
      setEndingPairingId(null);
    }
  }

  async function loadRelationships() {
    try {
      const rows = await api<MentorshipRelationship[]>(`/orgs/${org.id}/mentorship-relationships`);
      setRelationships(rows);
    } catch {
      // quietly leave empty rather than blocking the rest of the page
    }
  }

  function startNewRelationship(type: string) {
    setNewRelationshipType(type);
    setNewRelationshipName("");
    setNewRelationshipParticipants([]);
  }

  async function createRelationship() {
    if (!newRelationshipType || newRelationshipParticipants.length < 2) return;
    if (newRelationshipType === "reciprocal" && newRelationshipParticipants.length !== 2) {
      alert("A reciprocal pair needs exactly two peers.");
      return;
    }
    setCreatingRelationship(true);
    try {
      await api(`/orgs/${org.id}/mentorship-relationships`, {
        method: "POST",
        body: JSON.stringify({
          relationship_type: newRelationshipType,
          name: newRelationshipName,
          participants: newRelationshipParticipants.map((p) => ({
            application_id: p.application_id,
            role: newRelationshipType === "reciprocal" ? "peer" : p.role,
          })),
        }),
      });
      setNewRelationshipType(null);
      loadRelationships();
    } catch (err: any) {
      alert(err.message || "Couldn't create that relationship.");
    } finally {
      setCreatingRelationship(false);
    }
  }

  async function endRelationship(relationshipId: number) {
    const reason = prompt("Why is this ending? (optional)");
    if (reason === null) return;
    try {
      await api(`/orgs/${org.id}/mentorship-relationships/${relationshipId}/end`, {
        method: "POST", body: JSON.stringify({ reason }),
      });
      loadRelationships();
    } catch (err: any) {
      alert(err.message || "Couldn't end that relationship.");
    }
  }

  async function loadSchedules(assignmentId: number) {
    if (scheduleOpenFor === assignmentId) {
      setScheduleOpenFor(null);
      return;
    }
    setScheduleOpenFor(assignmentId);
    setNewScheduleAt(""); setNewScheduleDuration(30);
    try {
      const rows = await api<MentorMeetingSchedule[]>(`/orgs/${org.id}/mentor-assignments/${assignmentId}/schedule`);
      setSchedules((prev) => ({ ...prev, [assignmentId]: rows }));
    } catch (err: any) {
      alert(err.message || "Couldn't load the schedule.");
    }
  }

  async function createSchedule(assignmentId: number) {
    if (!newScheduleAt) return;
    setSchedulingMeeting(true);
    try {
      // datetime-local gives a value with no timezone offset -- treated
      // as local time and converted to a real ISO instant before
      // sending, since the backend stores/compares real UTC instants.
      const iso = new Date(newScheduleAt).toISOString();
      await api(`/orgs/${org.id}/mentor-assignments/${assignmentId}/schedule`, {
        method: "POST",
        body: JSON.stringify({ scheduled_at: iso, duration_minutes: newScheduleDuration }),
      });
      setNewScheduleAt("");
      const rows = await api<MentorMeetingSchedule[]>(`/orgs/${org.id}/mentor-assignments/${assignmentId}/schedule`);
      setSchedules((prev) => ({ ...prev, [assignmentId]: rows }));
    } catch (err: any) {
      alert(err.message || "Couldn't schedule that meeting.");
    } finally {
      setSchedulingMeeting(false);
    }
  }

  async function cancelSchedule(scheduleId: number, assignmentId: number) {
    if (!confirm("Cancel this scheduled meeting?")) return;
    try {
      await api(`/orgs/${org.id}/mentor-meeting-schedules/${scheduleId}`, { method: "DELETE" });
      const rows = await api<MentorMeetingSchedule[]>(`/orgs/${org.id}/mentor-assignments/${assignmentId}/schedule`);
      setSchedules((prev) => ({ ...prev, [assignmentId]: rows }));
    } catch (err: any) {
      alert(err.message || "Couldn't cancel that meeting.");
    }
  }

  return (
    <div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Mentor assignments</h3>
        <p className="hint" style={{ marginTop: -6, marginBottom: 20 }}>
          Pair a specific employee with one mentor from the pool. Assigned mentors show up
          on the employee's Job Buddy page with a direct "Request an intro" — not just left in
          the general contact list. Use "Suggest mentors (AI)" for a data-informed starting point
          based on the employee's resume and stated career goal — you still make the final call.
          To add a new mentor to the pool, manage contacts in Org Buddy and check
          "Available as a mentor."
        </p>

        {employees.length === 0 ? (
          <div className="empty-state" style={{ marginTop: 8 }}>
            No employees have joined yet — once they do, they'll show up here ready to be
            paired with a mentor.
          </div>
        ) : (
          employees.map((e) => {
            const mentorPool = contacts.filter((c) => c.is_mentor && (c.department_id === null || c.department_id === e.department_id));
            const ranked = suggestions[e.application_id];
            const employeeMeetings = e.mentor_assignment_id ? meetings[e.mentor_assignment_id] : undefined;
            const assignmentSchedules = e.mentor_assignment_id ? schedules[e.mentor_assignment_id] : undefined;
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
                    {e.mentor_assignment_id && !e.mentor_ended_at && (
                      <button className="btn btn-ghost btn-sm" onClick={() => loadSchedules(e.mentor_assignment_id!)}>
                        {scheduleOpenFor === e.mentor_assignment_id ? "Hide schedule" : "Schedule"}
                      </button>
                    )}
                    {e.mentor_assignment_id && (
                      e.mentor_ended_at ? (
                        <span className="pill" style={{ fontSize: "0.75rem" }}>Ended</span>
                      ) : (
                        <button
                          className="btn btn-ghost btn-sm"
                          disabled={endingPairingId === e.mentor_assignment_id}
                          onClick={() => endPairing(e.mentor_assignment_id!)}
                        >
                          {endingPairingId === e.mentor_assignment_id ? "Ending…" : "End pairing"}
                        </button>
                      )
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
                    <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
                      <div className="field" style={{ marginBottom: 0 }}>
                        <label>Date</label>
                        <input type="date" value={newMeetingDate} onChange={(ev) => setNewMeetingDate(ev.target.value)} />
                      </div>
                      <div className="field" style={{ marginBottom: 0 }}>
                        <label>Use a template</label>
                        <select
                          value=""
                          onChange={(ev) => {
                            const tpl = MEETING_AGENDA_TEMPLATES.find((t) => t.label === ev.target.value);
                            if (tpl) setNewMeetingNotes(tpl.text);
                          }}
                          style={{ width: 170 }}
                        >
                          <option value="">Pick a template…</option>
                          {MEETING_AGENDA_TEMPLATES.map((t) => <option key={t.label} value={t.label}>{t.label}</option>)}
                        </select>
                      </div>
                      <div className="field" style={{ marginBottom: 0, flex: 1, minWidth: 200 }}>
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

                {e.mentor_assignment_id && scheduleOpenFor === e.mentor_assignment_id && (
                  <div style={{ marginTop: 10, marginLeft: 42 }}>
                    {assignmentSchedules === undefined ? (
                      <p className="hint">Loading…</p>
                    ) : assignmentSchedules.length === 0 ? (
                      <p className="hint">Nothing scheduled yet.</p>
                    ) : (
                      assignmentSchedules.map((s) => (
                        <div key={s.id} style={{ padding: "6px 0", borderBottom: "1px solid var(--border, #eee)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <div>
                            <div style={{ fontWeight: 600 }}>
                              {new Date(s.scheduled_at).toLocaleString()} · {s.duration_minutes} min
                            </div>
                            <div className="hint">
                              {s.calendar_event_created ? "✓ Calendar invite sent" : "No calendar invite (nobody connected yet)"}
                            </div>
                          </div>
                          <button className="btn btn-ghost btn-sm" onClick={() => cancelSchedule(s.id, e.mentor_assignment_id!)}>
                            Cancel
                          </button>
                        </div>
                      ))
                    )}
                    <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
                      <div className="field" style={{ marginBottom: 0 }}>
                        <label>Date &amp; time</label>
                        <input type="datetime-local" value={newScheduleAt} onChange={(ev) => setNewScheduleAt(ev.target.value)} />
                      </div>
                      <div className="field" style={{ marginBottom: 0 }}>
                        <label>Duration</label>
                        <select value={newScheduleDuration} onChange={(ev) => setNewScheduleDuration(Number(ev.target.value))}>
                          <option value={15}>15 min</option>
                          <option value={30}>30 min</option>
                          <option value={45}>45 min</option>
                          <option value={60}>60 min</option>
                        </select>
                      </div>
                      <button
                        className="btn btn-primary btn-sm"
                        disabled={schedulingMeeting || !newScheduleAt}
                        onClick={() => createSchedule(e.mentor_assignment_id!)}
                      >
                        {schedulingMeeting ? "Scheduling…" : "Schedule meeting"}
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
        <div className="card-row">
          <h3 style={{ marginTop: 0 }}>Group & reciprocal mentoring</h3>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => startNewRelationship("group")}>+ New group</button>
            <button className="btn btn-ghost btn-sm" onClick={() => startNewRelationship("reciprocal")}>+ New peer pair</button>
          </div>
        </div>
        <p className="hint" style={{ marginTop: -6, marginBottom: 20 }}>
          Separate from the 1:1 mentor assignments above — a group has one or more mentors and
          several mentees; a reciprocal pair has two peers with no hierarchy between them.
        </p>

        {newRelationshipType && (
          <div style={{ padding: 12, border: "1px solid var(--border, #eee)", borderRadius: 6, marginBottom: 12 }}>
            <p style={{ fontWeight: 600, marginTop: 0, marginBottom: 8 }}>
              {newRelationshipType === "group" ? "New group" : "New peer pair"}
            </p>
            <div className="field">
              <label>Name (optional)</label>
              <input value={newRelationshipName} onChange={(e) => setNewRelationshipName(e.target.value)}
                     placeholder={newRelationshipType === "group" ? "e.g. New Grad Cohort — Fall 2026" : ""} />
            </div>
            <p className="hint" style={{ marginBottom: 6 }}>
              {newRelationshipType === "group" ? "Pick participants and their role:" : "Pick exactly two peers:"}
            </p>
            {employees.map((e) => {
              const selected = newRelationshipParticipants.find((p) => p.application_id === e.application_id);
              return (
                <div key={e.application_id} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <input
                    type="checkbox"
                    style={{ width: "auto" }}
                    checked={!!selected}
                    onChange={(ev) => {
                      if (ev.target.checked) {
                        setNewRelationshipParticipants((prev) => [...prev, {
                          application_id: e.application_id,
                          role: newRelationshipType === "reciprocal" ? "peer" : "mentee",
                        }]);
                      } else {
                        setNewRelationshipParticipants((prev) => prev.filter((p) => p.application_id !== e.application_id));
                      }
                    }}
                  />
                  <span style={{ flex: 1 }}>{e.user_full_name}</span>
                  {newRelationshipType === "group" && selected && (
                    <select
                      value={selected.role}
                      onChange={(ev) => setNewRelationshipParticipants((prev) =>
                        prev.map((p) => p.application_id === e.application_id ? { ...p, role: ev.target.value } : p)
                      )}
                      style={{ width: 120 }}
                    >
                      <option value="mentor">Mentor</option>
                      <option value="mentee">Mentee</option>
                    </select>
                  )}
                </div>
              );
            })}
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <button
                className="btn btn-primary btn-sm"
                disabled={creatingRelationship || newRelationshipParticipants.length < 2}
                onClick={createRelationship}
              >
                {creatingRelationship ? "Creating…" : "Create"}
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => setNewRelationshipType(null)}>Cancel</button>
            </div>
          </div>
        )}

        {relationships.length === 0 ? (
          <div className="empty-state" style={{ marginTop: 8 }}>
            No group or reciprocal relationships yet — use "New group" or "New peer pair" above
            to build one from your current employees.
          </div>
        ) : (
          relationships.map((r) => (
            <div key={r.id} style={{ padding: "8px 0", borderBottom: "1px solid var(--border, #eee)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontWeight: 600 }}>
                    {r.name || (r.relationship_type === "group" ? "Untitled group" : "Peer pair")}
                    <span className="pill" style={{ marginLeft: 8, fontSize: "0.75rem" }}>{r.relationship_type}</span>
                    {r.ended_at && <span className="pill" style={{ marginLeft: 6, fontSize: "0.75rem" }}>Ended</span>}
                  </div>
                  <div className="hint">
                    {r.participants.map((p) => `${p.user_full_name} (${p.role})`).join(", ")}
                  </div>
                </div>
                {!r.ended_at && (
                  <button className="btn btn-ghost btn-sm" onClick={() => endRelationship(r.id)}>End</button>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
