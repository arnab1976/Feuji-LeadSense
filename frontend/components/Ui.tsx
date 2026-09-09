"use client";

import { useEffect, useState } from "react";
import { getUser, signIn, clearSession, SessionUser } from "@/lib/api";

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
 * Gate every page behind a session. In dev mode this posts to /auth/dev-token;
 * point it at MSAL for Entra ID and the rest of the app is unchanged.
 */
export function RequireSession({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    tenant: "feuji-revops",
    role: "tenant_admin",
    email: "arnab.das@feuji.com",
    name: "Arnab Das",
  });

  useEffect(() => {
    setUser(getUser());
    setReady(true);
  }, []);

  if (!ready) return <div className="empty">Loading…</div>;

  if (!user) {
    return (
      <div className="signin">
        <div className="card">
          <h2>Sign in to LeadSense</h2>
          <p className="hint">
            Local development mode. Pick a tenant and role to see how permissions
            change what the portal allows.
          </p>
          <Notice kind="error">{error}</Notice>
          <div className="field">
            <label>Tenant</label>
            <select
              value={form.tenant}
              onChange={(e) => setForm({ ...form, tenant: e.target.value })}
            >
              <option value="feuji-revops">Feuji Revenue Operations</option>
              <option value="northwind">Northwind Capital Partners</option>
            </select>
          </div>
          <div className="field">
            <label>Role</label>
            <select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
            >
              <option value="tenant_admin">Tenant admin</option>
              <option value="sales_manager">Sales manager</option>
              <option value="campaign_manager">Campaign manager</option>
              <option value="reviewer">Reviewer</option>
              <option value="analyst">Analyst</option>
              <option value="read_only">Read only</option>
            </select>
          </div>
          <div className="field">
            <label>Name</label>
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Email</label>
            <input
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </div>
          <button
            onClick={async () => {
              try {
                setError("");
                const u = await signIn(form.tenant, form.role, form.email, form.name);
                setUser(u);
              } catch (e: any) {
                setError(
                  e?.message ||
                    "Sign-in failed. Is the API running on port 8000, and has `make seed` been run?"
                );
              }
            }}
          >
            Sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="toolbar">
        <span className="small muted">
          {user.tenant_name} · {user.name} ·{" "}
          <Badge kind="agent">{user.role.replace("_", " ")}</Badge>
        </span>
        <span className="spacer" />
        <button
          className="ghost small"
          onClick={() => {
            clearSession();
            location.reload();
          }}
        >
          Sign out
        </button>
      </div>
      {children}
    </>
  );
}
