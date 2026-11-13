"use client";

import { AdminOnly } from "@/components/admin-only";
import { PageHeader } from "@/components/page-header";
import { usePermissions } from "@/features/auth/api";

import { useAuditLog } from "../api";

import { AuditLogPanel, useActionFilter } from "./audit-log-panel";

export function AuditScreen() {
  const [input, action, setInput] = useActionFilter();
  const { user, admin } = usePermissions();
  const q = useAuditLog(action || undefined, admin);

  return (
    <>
      <PageHeader
        title="Audit log"
        description="Everything on this server, append-only: imports, generations, runs, providers, keys, users and sign-ins. Who did what, to which object, from where."
      />
      {user && !admin ? (
        <AdminOnly what="The audit log" />
      ) : (
        <AuditLogPanel
          query={q}
          input={input}
          action={action}
          setInput={setInput}
          emptyText="Imports, generations, runs, provider changes, API keys, user changes and sign-ins are recorded here as they happen."
        />
      )}
    </>
  );
}
