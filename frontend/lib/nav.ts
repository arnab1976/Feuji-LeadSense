export const PRIMARY_NAV = [
  { href: "/workflow", label: "Workflow" },
  { href: "/dashboard", label: "Executive dashboard" },
  { href: "/agents", label: "Agent catalog" },
  { href: "/analytics", label: "Agent monitor" },
] as const;

export const JOURNEY_NAV = [
  { href: "/sources", label: "Sources" },
  { href: "/leads", label: "Leads" },
  { href: "/verification", label: "Verification" },
  { href: "/segments", label: "Segments" },
  { href: "/campaigns", label: "Campaigns" },
  { href: "/studio", label: "Email studio" },
] as const;

export function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("");
}

export function roleLabel(role: string) {
  return role
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function tenantCode(tenantId: string) {
  const digits = tenantId.replace(/\D/g, "").slice(-3).padStart(3, "0") || "001";
  return `TEN-${digits}`;
}

export function isNavActive(pathname: string, href: string) {
  if (href === "/dashboard") return pathname === "/dashboard";
  if (href === "/workflow") return pathname === "/workflow" || pathname.startsWith("/workflow/");
  return pathname === href || pathname.startsWith(`${href}/`);
}
