const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export function setToken(token: string) {
  localStorage.setItem("token", token);
}

export function clearToken() {
  localStorage.removeItem("token");
}

// A single global listener the dashboard layout registers itself with
// (see QuotaLimitModal) -- lets api() surface a 429 (quota/plan-limit
// reached) as a real, hard-to-miss modal from a single place, instead
// of every page needing its own quota-handling logic. Existing
// per-page inline error handling (setError, etc.) keeps working too --
// this is additive, not a replacement, since api() still throws the
// error either way.
let onQuotaLimit: ((message: string) => void) | null = null;

export function setQuotaLimitListener(fn: ((message: string) => void) | null) {
  onQuotaLimit = fn;
}

// Exported directly (not just used internally by api() below) because
// not every quota-reached signal is a 429 -- /pipeline/match
// deliberately returns 200 with usage_limit_reached: true in the body
// when it stops early mid-run, so it can still show whatever partial
// results it found rather than failing the whole request. Pages need
// a way to trigger the same modal for that case too.
export function showQuotaLimitModal(message: string) {
  onQuotaLimit?.(message);
}

export async function api<T = any>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const isFormData = options.body instanceof FormData;

  const headers: Record<string, string> = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("Not authenticated");
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response wasn't JSON — keep statusText
    }
    if (res.status === 429 && onQuotaLimit) {
      onQuotaLimit(typeof detail === "string" ? detail : "You've reached your plan's limit for this.");
    }
    throw new Error(detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// --- Types matching backend schemas ---

export interface User {
  id: number;
  email: string;
  full_name: string;
  phone: string;
  location: string;
  linkedin_url: string;
  portfolio_url: string;
  notify_email: string;
  auto_submit: boolean;
  notification_preference: string;
  notification_min_score: number;
  notification_channel: string;
  sms_consent: boolean;
  resume_text: string;
  subscription_tier: string;
  subscription_status: string;
  is_admin: boolean;
  admin_role: string;
}

export interface SavedResume {
  id: number;
  label: string;
  resume_text: string;
  is_default: boolean;
  created_at: string;
}

export interface SearchProfile {
  id: number;
  name: string;
  titles: string[];
  locations: string[];
  seniority: string[];
  min_match_score: number;
  exclude_companies: string[];
  keywords_required: string[];
  keywords_excluded: string[];
  active: boolean;
}

export interface Application {
  id: number;
  status: string;
  matched_profile: string;
  match_score: number;
  match_reason: string;
  tailored_resume_path: string;
  notes: string;
  created_at: string;
  submitted_at: string | null;
  job_title: string;
  job_company: string;
  job_location: string;
  job_url: string;
  organization_id: number | null;
  organization_logo_url: string;
  tailoring_rationale: string;
  has_tailored_resume_data: boolean;
}

export interface Usage {
  tier: string;
  matches_used: number;
  matches_limit: number;
  tailored_resumes_used: number;
  tailored_resumes_limit: number;
  interview_preps_used: number;
  interview_preps_limit: number;
  onboarding_plans_used: number;
  onboarding_plans_limit: number;
  job_buddy_messages_used: number;
  job_buddy_messages_limit: number;
}

export interface InterviewPrep {
  id: number;
  application_id: number;
  brief: string;
  created_at: string;
}

export interface OnboardingPlan {
  id: number;
  application_id: number;
  plan: string;
  created_at: string;
}

export interface Organization {
  id: number;
  name: string;
  join_code: string;
  created_at: string;
  is_sandbox: boolean;
  logo_url: string;
}

export interface OrgContent {
  id: number;
  title: string;
  content: string;
  department_id: number | null;
  media_url: string;
  created_at: string;
}

export interface OrgUsageStats {
  employees_joined: number;
  plans_generated: number;
  total_messages: number;
  avg_messages_per_employee: number;
}

export interface ChecklistItemStats {
  item_id: number;
  title: string;
  total_assigned: number;
  total_completed: number;
  completion_rate: number;
}

export interface LessonQuizStats {
  lesson_id: number;
  title: string;
  quiz_question: string;
  total_attempts: number;
  correct_count: number;
  correct_rate: number;
}

export interface QAGapStats {
  question: string;
  count: number;
}

export interface DepartmentStats {
  department_id: number | null;
  department_name: string;
  total_employees: number;
  completed_onboarding: number;
  completion_rate: number;
}

export interface OrgAnalytics {
  total_employees: number;
  avg_days_to_complete_onboarding: number | null;
  checklist_items: ChecklistItemStats[];
  lesson_quizzes: LessonQuizStats[];
  qa_gaps: QAGapStats[];
  departments: DepartmentStats[];
}

export interface OrgRosterEntry {
  id: number;
  email: string;
  title: string;
  tenure: string;
  department_id: number | null;
  manager_email: string;
  joined: boolean;
  created_at: string;
}

export interface OrgBilling {
  plan: string;
  subscription_status: string;
  included_seats: number;
  employees_joined: number;
  overage_seats: number;
  overage_cost_usd: number;
}

export interface OrgContact {
  id: number;
  name: string;
  email: string;
  description: string;
  department_id: number | null;
  is_mentor: boolean;
  created_at: string;
}

export interface MentorAssignment {
  id: number;
  name: string;
  email: string;
  description: string;
  assigned_at: string;
}

export interface CareerGoal {
  id: number;
  goal_text: string;
  created_at: string;
  achieved_at: string | null;
}

export interface Department {
  id: number;
  name: string;
  join_code: string;
  created_at: string;
}

export interface ChecklistItem {
  id: number;
  title: string;
  description: string;
  policy_content: string | null;
  department_id: number | null;
  order: number;
  media_url: string;
  created_at: string;
}

export interface ChecklistProgressItem {
  id: number;
  title: string;
  description: string;
  policy_content: string | null;
  media_url: string;
  completed: boolean;
  completed_at: string | null;
}

export interface KBArticle {
  id: number;
  category: string;
  title: string;
  content: string;
  updated_at: string;
}

export interface KBAskResponse {
  answer: string;
  sources: KBArticle[];
}

export interface JobBuddyMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface CompanyStats {
  company: string;
  applied_count: number;
  response_rate: number;
  avg_days_to_respond: number | null;
  recent_applications: number | null;
}

export interface PointsEvent {
  amount: number;
  reason: string;
  created_at: string;
}

export interface RiseIndexMe {
  rise_points: number;
  current_streak: number;
  longest_streak: number;
  recent_events: PointsEvent[];
}

export interface NearMiss {
  title: string;
  company: string;
  url: string;
  score: number;
  reason: string;
  matched_profile: string;
}

// --- Admin ---

export interface AdminUser {
  id: number;
  email: string;
  full_name: string;
  subscription_tier: string;
  subscription_status: string;
  is_admin: boolean;
  admin_role: string;
  is_suspended: boolean;
  suspended_reason: string;
  rise_points: number;
  current_streak: number;
  created_at: string;
}

export interface AdminRevenue {
  total_users: number;
  free_count: number;
  active_pro_count: number;
  mrr_estimate_usd: number;
  signups_this_week: number;
  signups_this_month: number;
}

export interface AdminUsageActionStat {
  count: number;
  estimated_cost_usd: number;
}

export interface AdminUsage {
  period: string;
  by_action: Record<string, AdminUsageActionStat>;
  total_estimated_cost_usd: number;
}

export interface AdminFailureActionStat {
  action: string;
  count: number;
}

export interface AdminErrors {
  period: string;
  by_action: AdminFailureActionStat[];
  total_failures: number;
}

export interface AdminSupportMessage {
  id: number;
  user_email: string;
  subject: string;
  message: string;
  status: string;
  admin_reply: string | null;
  replied_at: string | null;
  created_at: string;
}

export interface AdminOrganization {
  id: number;
  name: string;
  plan: string;
  subscription_status: string;
  included_seats: number;
  member_count: number;
  overage_seats: number;
  estimated_mrr_usd: number;
  created_at: string;
  is_sandbox: boolean;
}

export interface AdminJobSourceHealth {
  source: string;
  jobs_last_24h: number;
  jobs_last_7d: number;
  last_discovered_at: string | null;
  status: "healthy" | "stale" | "silent";
}

export interface AdminSystemHealth {
  job_sources: AdminJobSourceHealth[];
  total_jobs_in_pool: number;
}

export interface AdminFlaggedMessage {
  id: number;
  application_id: number;
  user_email: string;
  role: string;
  content: string;
  flag_reason: string;
  flag_resolved_at: string | null;
  created_at: string;
}

export interface OrgLesson {
  id: number;
  day_offset: number;
  title: string;
  content: string;
  quiz_question: string;
  quiz_answer: string;
  department_id: number | null;
  order: number;
  media_url: string;
  created_at: string;
}

export interface LessonDelivery {
  id: number;
  lesson_id: number;
  title: string;
  content: string;
  quiz_question: string;
  media_url: string;
  delivered_at: string;
  quiz_response: string | null;
  quiz_correct: boolean | null;
}

export interface OrgQALog {
  id: number;
  application_id: number;
  user_email: string;
  question: string;
  answer: string;
  matched_content: boolean;
  created_at: string;
}

export interface OrgAskResponse {
  answer: string;
  sources: string[];
}

export async function downloadFile(path: string, fallbackFilename: string) {
  const token = getToken();
  const res = await fetch(`${API_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    throw new Error("Couldn't download that file — it may not be ready yet.");
  }
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : fallbackFilename;

  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}
