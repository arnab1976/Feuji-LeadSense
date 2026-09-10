"use client";

import { usePathname } from "next/navigation";
import PortalShell from "@/components/PortalShell";

/**
 * Home stays bare. Every authenticated route uses the Workflow-style portal shell.
 * Workflow supplies its own shell (with agent roster), so it is also bare here.
 */
export default function ConditionalShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const bare =
    pathname === "/" ||
    pathname.startsWith("/workflow") ||
    pathname.startsWith("/verification");

  if (bare) return <>{children}</>;

  return <PortalShell>{children}</PortalShell>;
}
