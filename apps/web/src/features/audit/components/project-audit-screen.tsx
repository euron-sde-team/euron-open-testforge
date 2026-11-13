"use client";

import * as React from "react";

import { PageHeader } from "@/components/page-header";
import { SimpleSelect } from "@/components/ui/select";
import { useCurrentProject, useMembers } from "@/features/projects/api";

import { useProjectAudit } from "../api";

import { AuditLogPanel, useActionFilter } from "./audit-log-panel";

/** Common filters, so nobody has to know the action names. */
const QUICK = [
  { value: "", label: "Every action" },
  { value: "run.requested", label: "Runs started" },
  { value: "run.finished", label: "Runs finished" },
  { value: "generation.requested", label: "Tests generated" },
  { value: "import.created", label: "Code imported" },
  { value: "pull_request.imported", label: "Pull requests imported" },
  { value: "project.member_added", label: "Members added" },
];

/**
 * The project's append-only audit log, open to every member: every import, generation and
 * run (with its result and who triggered it) and every change, filtered by action or person.
 */
export function ProjectAuditScreen() {
  const { pid } = useCurrentProject();
  const members = useMembers(pid);
  const [actorId, setActorId] = React.useState("");
  const [input, action, setInput] = useActionFilter();
  const q = useProjectAudit(pid, { action, actorId });
  const quick = QUICK.some((o) => o.value === input) ? input : "";
  return (
    <>
      <PageHeader
        title="Audit log"
        description="Append-only: every import, generation and run with its result and who triggered it, and every change to the project. Nobody can edit or delete an entry."
      />
      <div className="mb-3 flex flex-col gap-2 sm:flex-row">
        <SimpleSelect aria-label="What happened" value={quick} onValueChange={setInput} options={QUICK} className="w-full sm:w-56" />
        <SimpleSelect
          aria-label="Person"
          value={actorId}
          onValueChange={setActorId}
          options={[{ value: "", label: "Everyone" }, ...(members.data ?? []).map((m) => ({ value: m.user_id, label: m.name }))]}
          className="w-full sm:w-56"
        />
      </div>
      <AuditLogPanel
        query={q}
        input={input}
        action={action}
        setInput={setInput}
        emptyText="Imports, generations, runs and changes in this project are recorded here as they happen."
      />
    </>
  );
}
