"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/workflow", label: "Workflow" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/sources", label: "Sources" },
  { href: "/leads", label: "Leads" },
  { href: "/verification", label: "Verification" },
  { href: "/segments", label: "Segments" },
  { href: "/campaigns", label: "Campaigns" },
  { href: "/studio", label: "Email studio" },
  { href: "/analytics", label: "Analytics" },
  { href: "/agents", label: "Agents" },
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <nav className="rail">
      <div className="brand">
        Lead<span>Sense</span>
      </div>
      <div className="tagline">Verified lead intelligence</div>
      {LINKS.map((link) => {
        const active =
          link.href === "/dashboard"
            ? pathname === "/dashboard"
            : pathname.startsWith(link.href);
        return (
          <Link key={link.href} href={link.href} className={active ? "active" : ""}>
            {link.label}
          </Link>
        );
      })}
      <div className="foot">v1.0 · multi-tenant</div>
    </nav>
  );
}
