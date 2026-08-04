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
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
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
  matches_used: number;
  matches_limit: number;
  tailored_resumes_used: number;
  tailored_resumes_limit: number;
}
