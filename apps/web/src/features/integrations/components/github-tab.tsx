"use client";

import { GithubIcon, RotateCwIcon, TriangleAlertIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { CopyButton } from "@/components/copy-button";
import { RoleNote } from "@/components/role-note";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { useUpdateProject } from "@/features/projects/api";
import { errorMessage } from "@/lib/api/errors";
import type { GitHubSecret, Project } from "@/lib/api/types";

import { useRotateGithubSecret } from "../api";

/** The project's GitHub repository, its token, and the webhook GitHub calls on pull requests. */
export function GithubTab({ project: p, canAdmin }: { project: Project; canAdmin: boolean }) {
  const update = useUpdateProject(p.id);
  const rotate = useRotateGithubSecret(p.id);
  const [repo, setRepo] = React.useState(p.github_repo ?? "");
  const [token, setToken] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [confirm, setConfirm] = React.useState(false);
  const [secret, setSecret] = React.useState<GitHubSecret | null>(null);
  const ro = !canAdmin;

  function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    update.mutate(
      { github_repo: repo.trim() || null, ...(token ? { github_token: token } : {}) },
      {
        onSuccess: () => {
          setToken("");
          toast.success("GitHub settings saved.");
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <div className="max-w-3xl space-y-4">
      {ro && <RoleNote>Only project admins connect GitHub and rotate the webhook secret.</RoleNote>}
      <form onSubmit={save} noValidate>
        <Surface>
          <SurfaceHeader title="Repository" description="Imports and pull requests use it when they name no other. A private repository needs a token with read access." />
          <div className="grid gap-4 px-5 pb-5 sm:grid-cols-2">
            <Field label="Repository" htmlFor="gh-repo" hint="owner/name">
              <Input id="gh-repo" disabled={ro} placeholder="euron-demo/python-shop" value={repo} onChange={(e) => setRepo(e.target.value)} />
            </Field>
            <Field label="Access token" htmlFor="gh-token" labelExtra={p.has_github_token ? <Chip tone="success">Stored</Chip> : undefined} hint="Sealed on the server and never shown again. Leave empty to keep it.">
              <Input id="gh-token" type="password" autoComplete="off" disabled={ro} placeholder={p.has_github_token ? "Stored, type to replace" : "github_pat_..."} value={token} onChange={(e) => setToken(e.target.value)} />
            </Field>
          </div>
          {canAdmin && (
            <div className="flex flex-col gap-2 rounded-b-[14px] bg-muted/50 px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between">
              <div>{error && <FieldError>{error}</FieldError>}</div>
              <Button type="submit" disabled={update.isPending}>
                {update.isPending ? "Saving..." : "Save GitHub settings"}
              </Button>
            </div>
          )}
        </Surface>
      </form>
      <Surface>
        <SurfaceHeader
          title="Pull request webhook"
          description="Point a GitHub webhook (pull_request events) at this project, and every opened or updated pull request is imported and scoped automatically. The payload is verified with the secret."
        />
        <div className="flex flex-col gap-3 px-5 pb-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-[12.5px] text-muted-foreground">Rotating creates a new secret; the old one stops working at once. The secret is shown once.</p>
          {canAdmin && (
            <Button variant="outline" onClick={() => setConfirm(true)} className="shrink-0">
              <RotateCwIcon />
              Rotate webhook secret
            </Button>
          )}
        </div>
      </Surface>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Rotate the webhook secret?"
        description="GitHub deliveries signed with the old secret are refused from now on. Update the webhook on GitHub with the new one."
        confirmLabel="Rotate secret"
        destructive={false}
        pending={rotate.isPending}
        onConfirm={() =>
          rotate.mutate(undefined, {
            onSuccess: (s) => {
              setConfirm(false);
              setSecret(s);
            },
            onError: (err) => toast.error(errorMessage(err)),
          })
        }
      />
      <Dialog open={!!secret} onOpenChange={(o) => !o && setSecret(null)}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <GithubIcon className="size-4" /> Set up the webhook on GitHub
            </DialogTitle>
            <DialogDescription>Repository settings, Webhooks, Add webhook. Content type application/json, events: Pull requests.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <Field label="Payload URL">
              <div className="flex items-center gap-2 rounded-xl bg-muted p-2 pl-3">
                <code className="min-w-0 flex-1 truncate font-mono text-[12.5px]">{secret?.url}</code>
                <CopyButton value={secret?.url ?? ""} />
              </div>
            </Field>
            <Field label="Secret">
              <div className="flex items-center gap-2 rounded-xl bg-muted p-2 pl-3">
                <code className="min-w-0 flex-1 truncate font-mono text-[12.5px]" data-qa="github-secret">
                  {secret?.secret}
                </code>
                <CopyButton value={secret?.secret ?? ""} variant="default" />
              </div>
            </Field>
            <p className="flex items-start gap-2 text-[12.5px] text-warning">
              <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
              This is the only time the secret is shown. Rotate again if you lose it.
            </p>
          </DialogBody>
          <DialogFooter>
            <Button onClick={() => setSecret(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
