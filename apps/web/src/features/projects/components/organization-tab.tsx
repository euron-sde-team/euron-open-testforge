"use client";

import { Building2Icon, Trash2Icon, UserPlusIcon, UsersIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { RoleNote } from "@/components/role-note";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { Field, FieldError, FieldHint } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { AuditLogPanel, useActionFilter } from "@/features/audit/components/audit-log-panel";
import { usePermissions } from "@/features/auth/api";
import { useAddOrgMember, useOrg, useOrgAudit, useOrgMembers, useRemoveOrgMember, useUpdateOrg, useUpdateOrgMember } from "@/features/orgs/api";
import { errorMessage } from "@/lib/api/errors";
import type { Org, OrgMember, OrgRole } from "@/lib/api/types";
import { formatNumber, formatRelative, initials } from "@/lib/format";
import { canOrg, ORG_ROLE_DESCRIPTION, ORG_ROLE_LABEL, ORG_ROLES } from "@/lib/roles";

const ROLE_OPTIONS = ORG_ROLES.map((r) => ({ value: r, label: ORG_ROLE_LABEL[r] }));
const ROLE_TONE = { owner: "primary", admin: "info", member: "neutral" } as const;

export function OrganizationTab({ orgId }: { orgId: string }) {
  const q = useOrg(orgId);
  if (q.isPending) return <Skeleton className="h-64 max-w-3xl rounded-[14px]" />;
  if (q.isError)
    return (
      <div className="surface max-w-3xl">
        <ErrorState error={q.error} title="The organization could not be loaded" onRetry={() => void q.refetch()} />
      </div>
    );
  const org = q.data;
  const manage = canOrg(org.role, "admin");
  return (
    <div className="max-w-3xl space-y-4">
      {!manage && (
        <RoleNote>
          You are a member of {org.name}. Organization admins and owners manage its members and read its audit log.
        </RoleNote>
      )}
      <OrgAbout org={org} />
      <OrgMembers org={org} manage={manage} />
      {manage && <OrgAudit orgId={org.id} />}
    </div>
  );
}

function OrgAbout({ org }: { org: Org }) {
  const update = useUpdateOrg(org.id);
  const [name, setName] = React.useState(org.name);
  const [error, setError] = React.useState<string | null>(null);
  const owner = canOrg(org.role, "owner");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return setError("The organization needs a name.");
    setError(null);
    update.mutate({ name: name.trim() }, { onSuccess: () => toast.success("Organization renamed."), onError: (err) => setError(errorMessage(err)) });
  }

  return (
    <Surface>
      <SurfaceHeader
        title={
          <span className="flex items-center gap-2">
            <Building2Icon className="size-4 text-subtle" />
            {org.name}
          </span>
        }
        description={`${formatNumber(org.projects ?? 0)} projects, ${formatNumber(org.members ?? 0)} members. Created ${formatRelative(org.created_at)}.`}
        action={<Chip tone={ROLE_TONE[org.role ?? "member"]}>You are {ORG_ROLE_LABEL[org.role ?? "member"].toLowerCase()}</Chip>}
      />
      {owner && (
        <form onSubmit={submit} noValidate className="px-5 pb-4">
          <Field label="Name" htmlFor="org-name" error={error}>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input id="org-name" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
              <Button type="submit" variant="outline" disabled={update.isPending || name.trim() === org.name}>
                {update.isPending ? "Saving..." : "Rename"}
              </Button>
            </div>
          </Field>
        </form>
      )}
    </Surface>
  );
}

function OrgMembers({ org, manage }: { org: Org; manage: boolean }) {
  const q = useOrgMembers(org.id);
  const { user } = usePermissions();
  const update = useUpdateOrgMember(org.id);
  const remove = useRemoveOrgMember(org.id);
  const [removing, setRemoving] = React.useState<OrgMember | null>(null);
  const list = q.data ?? [];
  const owner = canOrg(org.role, "owner");

  return (
    <>
      {manage && <AddOrgMember orgId={org.id} owner={owner} />}
      <Surface className="overflow-hidden">
        <SurfaceHeader title="Organization members" description="People in the organization can be added to its projects." />
        {q.isPending ? (
          <TableSkeleton rows={3} cols={3} />
        ) : q.isError ? (
          <ErrorState compact error={q.error} title="Members could not be loaded" onRetry={() => void q.refetch()} />
        ) : list.length === 0 ? (
          <EmptyState compact icon={UsersIcon} title="No members" description="Add people by email; they can then be added to projects." />
        ) : (
          <ul className="divide-y divide-hairline px-5 pb-2">
            {list.map((m) => {
              const self = m.user_id === user?.id;
              // Only owners hand out or take away ownership.
              const editable = manage && !self && (owner || m.role !== "owner");
              return (
                <li key={m.user_id} className="flex flex-wrap items-center gap-3 py-3 sm:flex-nowrap">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-soft text-[11.5px] font-semibold text-primary">{initials(m.name)}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 text-[13.5px] font-medium">
                      <span className="truncate">{m.name}</span>
                      {self && <Chip tone="primary">You</Chip>}
                    </div>
                    <div className="truncate text-[12px] text-muted-foreground">
                      {m.email}, joined {formatRelative(m.created_at)}
                    </div>
                  </div>
                  {editable ? (
                    <div className="flex items-center gap-1.5">
                      <SimpleSelect
                        aria-label={`Organization role for ${m.name}`}
                        size="sm"
                        className="w-28"
                        value={m.role}
                        options={owner ? ROLE_OPTIONS : ROLE_OPTIONS.filter((o) => o.value !== "owner")}
                        onValueChange={(v) =>
                          v &&
                          v !== m.role &&
                          update.mutate(
                            { userId: m.user_id, role: v as OrgRole },
                            {
                              onSuccess: () => toast.success(`${m.name} is now ${ORG_ROLE_LABEL[v as OrgRole].toLowerCase()}.`),
                              onError: (err) => toast.error(errorMessage(err)),
                            },
                          )
                        }
                      />
                      <Button variant="subtle" size="icon-xs" aria-label={`Remove ${m.name}`} onClick={() => setRemoving(m)}>
                        <Trash2Icon />
                      </Button>
                    </div>
                  ) : (
                    <Chip tone={ROLE_TONE[m.role]}>{ORG_ROLE_LABEL[m.role]}</Chip>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        <dl className="grid gap-2 px-5 pt-2 pb-5 sm:grid-cols-3">
          {ORG_ROLES.map((r) => (
            <div key={r} className="rounded-xl bg-muted/70 px-4 py-3">
              <dt className="text-[13px] font-semibold">{ORG_ROLE_LABEL[r]}</dt>
              <dd className="mt-0.5 text-[12.5px] leading-relaxed text-muted-foreground">{ORG_ROLE_DESCRIPTION[r]}</dd>
            </div>
          ))}
        </dl>
      </Surface>
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={`Remove ${removing?.name ?? "this member"} from ${org.name}?`}
        description="They lose access to every project in this organization at once. Their account stays."
        confirmLabel="Remove"
        pending={remove.isPending}
        onConfirm={() =>
          removing &&
          remove.mutate(removing.user_id, {
            onSuccess: () => {
              toast.success(`${removing.name} removed.`);
              setRemoving(null);
            },
            onError: (err) => {
              toast.error(errorMessage(err));
              setRemoving(null);
            },
          })
        }
      />
    </>
  );
}

function AddOrgMember({ orgId, owner }: { orgId: string; owner: boolean }) {
  const add = useAddOrgMember(orgId);
  const [email, setEmail] = React.useState("");
  const [name, setName] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [role, setRole] = React.useState<OrgRole>("member");
  const [error, setError] = React.useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) return setError("Enter the email address they sign in with.");
    if (password && !name.trim()) return setError("Add their name too, so the new account has one.");
    setError(null);
    add.mutate(
      { email: email.trim(), role, name: name.trim() || null, password: password || null },
      {
        onSuccess: (m) => {
          toast.success(password ? `${m.name} can now sign in. Share the password privately.` : `${m.name} added.`);
          setEmail("");
          setName("");
          setPassword("");
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <Surface>
      <SurfaceHeader title="Add someone to the organization" description="An existing account by email, or create one by also giving a name and an initial password." />
      <form onSubmit={submit} noValidate className="space-y-3 px-5 pb-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Email" htmlFor="om-email">
            <Input id="om-email" type="email" placeholder="maya@company.com" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Role" htmlFor="om-role">
            <SimpleSelect id="om-role" value={role} onValueChange={(v) => setRole((v || "member") as OrgRole)} options={owner ? ROLE_OPTIONS : ROLE_OPTIONS.filter((o) => o.value !== "owner")} />
          </Field>
          <Field label="Name (new accounts)" htmlFor="om-name">
            <Input id="om-name" autoComplete="off" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Initial password (new accounts)" htmlFor="om-pw">
            <Input id="om-pw" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          {error ? <FieldError>{error}</FieldError> : <FieldHint>{ORG_ROLE_LABEL[role]}: {ORG_ROLE_DESCRIPTION[role]}</FieldHint>}
          <Button type="submit" disabled={add.isPending} className="shrink-0">
            <UserPlusIcon />
            {add.isPending ? "Adding..." : "Add to organization"}
          </Button>
        </div>
      </form>
    </Surface>
  );
}

function OrgAudit({ orgId }: { orgId: string }) {
  const [input, action, setInput] = useActionFilter();
  const q = useOrgAudit(orgId, action || undefined);
  return (
    <div>
      <h2 className="mt-2 mb-2 text-[14px] font-semibold tracking-[-0.01em]">Organization audit log</h2>
      <AuditLogPanel
        query={q}
        input={input}
        action={action}
        setInput={setInput}
        emptyText="Changes in this organization's projects and members, and every query run in them, are recorded here as they happen."
      />
    </div>
  );
}
