/**
 * Demo credentials for the landing sign-in form.
 * Password is checked in the browser; the API still issues a dev JWT.
 */
export type DemoAccount = {
  email: string;
  password: string;
  name: string;
  role: string;
  tenant: string;
  tenantLabel: string;
};

export const DEMO_ACCOUNTS: DemoAccount[] = [
  {
    email: "arnab.das@feuji.com",
    password: "LeadSense2026",
    name: "Arnab Das",
    role: "sales_manager",
    tenant: "feuji-revops",
    tenantLabel: "Feuji Revenue Operations",
  },
  {
    email: "admin@feuji.com",
    password: "LeadSense2026",
    name: "Tenant Admin",
    role: "tenant_admin",
    tenant: "feuji-revops",
    tenantLabel: "Feuji Revenue Operations",
  },
  {
    email: "reviewer@feuji.com",
    password: "LeadSense2026",
    name: "Sam Reviewer",
    role: "reviewer",
    tenant: "feuji-revops",
    tenantLabel: "Feuji Revenue Operations",
  },
];

export function findDemoAccount(email: string, password: string) {
  const normalized = email.trim().toLowerCase();
  return DEMO_ACCOUNTS.find(
    (a) => a.email.toLowerCase() === normalized && a.password === password
  );
}
