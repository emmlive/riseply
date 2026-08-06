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
  resume_text: string;
  subscription_tier: string;
  subscription_status: string;
  is_admin: boolean;
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
}

export interface OrgContent {
  id: number;
  title: string;
  content: string;
  created_at: string;
}

export interface OrgUsageStats {
  employees_joined: number;
  plans_generated: number;
  total_messages: number;
  avg_messages_per_employee: number;
}

export interface OrgRosterEntry {
  id: number;
  email: string;
  title: string;
  tenure: string;
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
  created_at: string;
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
