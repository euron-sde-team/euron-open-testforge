import type { Metadata } from "next";

import { ProjectAuditScreen } from "@/features/audit/components/project-audit-screen";

export const metadata: Metadata = { title: "Audit log" };

export default function Page() {
  return <ProjectAuditScreen />;
}
