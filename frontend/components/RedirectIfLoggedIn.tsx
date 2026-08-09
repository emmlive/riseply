"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/api";

/**
 * Silently redirects to /dashboard if the person already has a token in
 * localStorage -- fixes the real bug behind "clicking Back home from
 * Security & Trust forces me to log in again": the homepage and login
 * page never checked for an existing session, so an already-logged-in
 * person landing on either got shown marketing copy or a blank login
 * form instead of being sent straight back in. Their token was never
 * actually cleared -- the app just never looked for it.
 *
 * Renders nothing itself; drop it into a page as a client-only child so
 * the page's own metadata export (needed for SEO) can stay a Server
 * Component.
 */
export default function RedirectIfLoggedIn() {
  const router = useRouter();

  useEffect(() => {
    if (getToken()) {
      router.replace("/dashboard");
    }
  }, [router]);

  return null;
}
