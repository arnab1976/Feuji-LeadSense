import type { Metadata } from "next";
import "./globals.css";
import ConditionalShell from "@/components/ConditionalShell";

export const metadata: Metadata = {
  title: "LeadSense",
  description:
    "Agentic AI lead intelligence and sales engagement platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ConditionalShell>{children}</ConditionalShell>
      </body>
    </html>
  );
}
