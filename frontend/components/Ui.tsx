"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getUser, SessionUser } from "@/lib/api";

export function Badge({ kind, children }: { kind: string; children: React.ReactNode }) {
  return <span className={`badge ${kind}`}>{children}</span>;
}

export function bandKind(band?: string | null) {
  switch ((band || "").toUpperCase()) {
    case "HOT": return "hot";
    case "HIGH": return "high";
    case "MEDIUM": return "medium";
    default: return "low";
  }
}

export function verdictKind(verdict?: string | null) {
  switch (verdict) {
    case "APPROVE_FOR_REVIEW": return "ok";
    case "NEEDS_REVIEW": return "warn";
    case "BLOCK": return "bad";
    default: return "neutral";
  }
}

export function statusKind(status?: string | null) {
  switch ((status || "").toUpperCase()) {
    case "MATCH": return "ok";
    case "MISMATCH": return "bad";
    case "NEEDS_REVIEW": return "warn";
    default: return "neutral";
  }
}

export function Notice({ kind, children }: { kind: string; children: React.ReactNode }) {
  if (!children) return null;
  return <div className={`notice ${kind}`}>{children}</div>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}

/**
 * Gate every page behind a session. Unauthenticated users are sent to the
 * landing sign-in page. Chrome (tenant / role / sign out) lives in PortalShell.
 */
export function RequireSession({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<SessionUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const session = getUser();
    setUser(session);
    setReady(true);
    if (!session) router.replace("/");
  }, [router]);

  if (!ready) return <div className="empty">Loading…</div>;
  if (!user) return <div className="empty">Redirecting to sign in…</div>;

  return <>{children}</>;
}
