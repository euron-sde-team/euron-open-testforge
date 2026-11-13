"use client";

import * as React from "react";
import { toast } from "sonner";

import { AdminOnly } from "@/components/admin-only";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Surface, SurfaceHeader } from "@/components/surface";
import { ThemeSelector } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { usePermissions } from "@/features/auth/api";
import { errorMessage } from "@/lib/api/errors";
import type { AdminSettings } from "@/lib/api/types";

import { useOrgSettings, useUpdateOrgSettings } from "../api";

function Toggle({ label, hint, checked, onChange, disabled }: { label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className="flex items-start gap-3 rounded-xl bg-muted/70 px-4 py-3">
      <Switch checked={checked} onCheckedChange={onChange} disabled={disabled} aria-label={label} className="mt-0.5" />
      <span>
        <span className="block text-[13px] font-medium">{label}</span>
        {hint && <span className="block text-[12px] leading-relaxed text-muted-foreground">{hint}</span>}
      </span>
    </label>
  );
}

export function SettingsScreen() {
  const { user, admin } = usePermissions();
  const q = useOrgSettings();
  if (user && !admin) return <AdminOnly what="Instance settings" />;
  return (
    <>
      <PageHeader title="Instance settings" description="How this TestForge server presents itself and who can create an account." />
      {q.isError ? (
        <div className="surface">
          <ErrorState error={q.error} title="Settings could not be loaded" onRetry={() => void q.refetch()} />
        </div>
      ) : !q.data ? (
        <Skeleton className="h-72 w-full max-w-3xl rounded-[14px]" />
      ) : (
        <SettingsForm settings={q.data} />
      )}
      <Surface className="mt-4 max-w-3xl">
        <SurfaceHeader title="Appearance" description="Your own preference on this device. It does not change anyone else's view." />
        <div className="px-5 pb-5">
          <ThemeSelector />
        </div>
      </Surface>
    </>
  );
}

function SettingsForm({ settings: s }: { settings: AdminSettings }) {
  const update = useUpdateOrgSettings();
  const [siteName, setSiteName] = React.useState(s.site_name);
  const [signup, setSignup] = React.useState(s.allow_signup);
  const [error, setError] = React.useState<string | null>(null);

  function save() {
    if (!siteName.trim()) return setError("The site name cannot be empty.");
    setError(null);
    update.mutate(
      { site_name: siteName.trim(), allow_signup: signup },
      { onSuccess: () => toast.success("Settings saved."), onError: (e) => setError(errorMessage(e)) },
    );
  }

  return (
    <form
      className="max-w-3xl"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      <Surface>
        <SurfaceHeader title="General" />
        <div className="grid gap-4 px-5 pb-5">
          <Field label="Site name" htmlFor="st-name" hint="Shown on the sign-in page, in the browser tab and in notice emails.">
            <Input id="st-name" maxLength={80} value={siteName} onChange={(e) => setSiteName(e.target.value)} />
          </Field>
          <Toggle
            label="Anyone can create an account"
            hint={
              signup
                ? "The sign-in page offers sign-up. Each new account gets its own organization; others add them to their projects."
                : "Only admins create accounts, on the Users page, and organization admins add members by email."
            }
            checked={signup}
            onChange={setSignup}
          />
        </div>
        <div className="flex flex-col gap-2 bg-muted/40 px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between">
          <div>{error && <FieldError>{error}</FieldError>}</div>
          <Button type="submit" disabled={update.isPending}>
            {update.isPending ? "Saving..." : "Save settings"}
          </Button>
        </div>
      </Surface>
    </form>
  );
}
