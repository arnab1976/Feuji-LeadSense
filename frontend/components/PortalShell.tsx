"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearSession, getUser, SessionUser } from "@/lib/api";
import {
  JOURNEY_NAV,
  PRIMARY_NAV,
  initials,
  isNavActive,
  roleLabel,
  tenantCode,
} from "@/lib/nav";

type PortalShellProps = {
  children: React.ReactNode;
  /** Optional left column (e.g. Workflow agent roster). */
  sidebar?: React.ReactNode;
  /** Hide the secondary journey strip. */
  hideJourney?: boolean;
};

export default function PortalShell({
  children,
  sidebar,
  hideJourney = false,
}: PortalShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<SessionUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const session = getUser();
    setUser(session);
    setReady(true);
    if (!session) router.replace("/");
  }, [router]);

  if (!ready || !user) {
    return <div className="home-boot">Loading LeadSense…</div>;
  }

  return (
    <div className="wf">
      <header className="wf-top">
        <div className="wf-brand">
          <Link href="/workflow" className="wf-logo">
            LeadSense
          </Link>
          <div className="wf-tenant">{user.tenant_name}</div>
        </div>

        <nav className="wf-tabs" aria-label="Primary">
          {PRIMARY_NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={isNavActive(pathname, item.href) ? "active" : ""}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="wf-user">
          <span className="wf-chip">{tenantCode(user.tenant_id)}</span>
          <span className="wf-chip">{roleLabel(user.role)}</span>
          <button
            type="button"
            className="wf-avatar"
            title="Sign out"
            onClick={() => {
              clearSession();
              router.replace("/");
            }}
          >
            {initials(user.name)}
          </button>
        </div>
      </header>

      {!hideJourney ? (
        <nav className="wf-journey" aria-label="Lead journey">
          <span className="wf-journey-label">Journey</span>
          {JOURNEY_NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={isNavActive(pathname, item.href) ? "active" : ""}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      ) : null}

      <div className={sidebar ? "wf-body" : "wf-body wf-body-solo"}>
        {sidebar ? <aside className="wf-roster">{sidebar}</aside> : null}
        <main className="wf-main portal-main">{children}</main>
      </div>
    </div>
  );
}
