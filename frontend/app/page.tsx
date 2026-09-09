"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getUser, signIn } from "@/lib/api";
import { DEMO_ACCOUNTS, findDemoAccount } from "@/lib/demo-users";

const TECH_STACK = [
  { name: "Next.js", detail: "App Router UI" },
  { name: "FastAPI", detail: "Python API" },
  { name: "LangGraph", detail: "Agent orchestration" },
  { name: "Celery", detail: "Async workers" },
];

const SOURCE_SYSTEMS = [
  { name: "Salesforce", detail: "CRM leads & accounts" },
  { name: "HubSpot", detail: "Marketing contacts" },
  { name: "Apollo.io", detail: "Prospect search" },
  { name: "ZoomInfo", detail: "Firmographic enrich" },
  { name: "Manual upload", detail: "CSV / Excel files" },
  { name: "CSV feed", detail: "URL or S3 ingest" },
  { name: "Web profile", detail: "Public profile scrape" },
];

export default function HomePage() {
  const router = useRouter();
  const [email, setEmail] = useState(DEMO_ACCOUNTS[0].email);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (getUser()) {
      router.replace("/workflow");
      return;
    }
    setChecking(false);
  }, [router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    const account = findDemoAccount(email, password);
    if (!account) {
      setError("Invalid email or password. Use one of the demo accounts shown below.");
      return;
    }
    setBusy(true);
    try {
      await signIn(account.tenant, account.role, account.email, account.name);
      router.push("/workflow");
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "Sign-in failed. Is the API running on port 8000?";
      setError(message);
      setBusy(false);
    }
  }

  if (checking) {
    return <div className="home-boot">Loading LeadSense…</div>;
  }

  return (
    <div className="home">
      <section className="home-brand">
        <div className="home-brand-inner">
          <p className="home-eyebrow">Agentic lead intelligence</p>
          <h1 className="home-title">
            Lead<span>Sense</span>
          </h1>
          <p className="home-lead">
            Turns raw prospect records into verified, enriched, scored and
            actionable sales intelligence — with a human gate on every material
            action before anyone is contacted.
          </p>
          <p className="home-body">
            Every lead is reconciled against its source before outreach. The
            pipeline pauses until a person resolves what did not match, so
            campaigns only ever touch approved truth.
          </p>

          <div className="home-powered">
            <h2>Powered by</h2>
            <ul className="home-stack">
              {TECH_STACK.map((item) => (
                <li key={item.name}>
                  <strong>{item.name}</strong>
                  <span>{item.detail}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="home-powered home-sources">
            <h2>Source systems supported</h2>
            <ul className="home-stack home-stack-sources">
              {SOURCE_SYSTEMS.map((item) => (
                <li key={item.name}>
                  <strong>{item.name}</strong>
                  <span>{item.detail}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="home-auth">
        <form className="home-auth-card" onSubmit={onSubmit}>
          <h2>Sign in</h2>
          <p className="home-auth-sub">
            Enter your demo credentials to open the Workflow portal.
          </p>

          {error ? <div className="notice error">{error}</div> : null}

          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <button type="submit" disabled={busy} className="home-submit">
            {busy ? "Signing in…" : "Sign in"}
          </button>

          <div className="home-hints">
            <h3>Demo hints</h3>
            <p>
              Password for every seeded account:{" "}
              <code>LeadSense2026</code>
            </p>
            <ul>
              {DEMO_ACCOUNTS.slice(0, 2).map((account) => (
                <li key={account.email}>
                  <button
                    type="button"
                    className="home-hint-fill"
                    onClick={() => {
                      setEmail(account.email);
                      setPassword(account.password);
                      setError("");
                    }}
                  >
                    <span className="home-hint-email">{account.email}</span>
                    <span className="home-hint-meta">
                      {account.role.replace("_", " ")} · {account.tenantLabel}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </form>
      </section>
    </div>
  );
}
