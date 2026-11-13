"use client";

import { BanIcon, CheckIcon, CpuIcon, FlaskConicalIcon, Loader2Icon } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Hint } from "@/components/hint";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import { Field, FieldError, Label } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { useCreateProvider, useProviders } from "@/features/providers/api";
import { errorMessage } from "@/lib/api/errors";
import type { Generation, TestKind } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDuration, plural } from "@/lib/format";
import { inFlight, TEST_KIND_DESCRIPTION, TEST_KIND_LABEL } from "@/lib/status";

import { useGenerate, useGeneration, useRefreshTests } from "../api";

const CODE_KINDS: TestKind[] = ["unit", "edge", "negative"];

/** The kinds a generation may ask for: API tests need an OpenAPI document, unit kinds need code. */
export function allowedKinds(specId?: string | null): TestKind[] {
  return specId ? ["api"] : CODE_KINDS;
}

export interface GenerateScope {
  unitIds?: string[];
  pullId?: string;
  specId?: string;
  /** Shown in the dialog's description: what the tests are for. */
  label: string;
}

/**
 * Ask the model for tests. Then follow the generation and show its result: how many tests
 * were proposed, and every test refused for having no meaningful assertion, with the reason.
 */
export function GenerateDialog({
  pid,
  open,
  onOpenChange,
  scope,
  canAdmin,
}: {
  pid: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scope: GenerateScope;
  canAdmin: boolean;
}) {
  const generate = useGenerate(pid);
  const providers = useProviders(pid);
  const addMock = useCreateProvider(pid);
  const kindsAllowed = allowedKinds(scope.specId);
  const [kinds, setKinds] = React.useState<TestKind[]>(kindsAllowed);
  const [providerId, setProviderId] = React.useState("");
  const [instructions, setInstructions] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [generationId, setGenerationId] = React.useState<string | null>(null);
  const enabled = (providers.data ?? []).filter((p) => p.enabled);
  const noProvider = providers.isSuccess && enabled.length === 0;

  React.useEffect(() => {
    if (!open) return;
    setKinds(allowedKinds(scope.specId));
    setInstructions("");
    setError(null);
    setGenerationId(null);
    setProviderId("");
  }, [open, scope.specId]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!kinds.length) return setError("Pick at least one kind of test.");
    setError(null);
    generate.mutate(
      {
        kinds,
        unit_ids: scope.unitIds?.length ? scope.unitIds : null,
        pull_id: scope.pullId ?? null,
        spec_id: scope.specId ?? null,
        provider_id: providerId || null,
        instructions: instructions.trim(),
      },
      { onSuccess: (g) => setGenerationId(g.id), onError: (err) => setError(errorMessage(err)) },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !generate.isPending && onOpenChange(o)}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{generationId ? "Generating tests" : "Generate tests"}</DialogTitle>
          <DialogDescription>{scope.label}</DialogDescription>
        </DialogHeader>
        {generationId ? (
          <GenerationResult pid={pid} generationId={generationId} onClose={() => onOpenChange(false)} />
        ) : (
          <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
            <DialogBody className="space-y-4">
              {noProvider && (
                <div role="status" className="flex flex-col gap-2 rounded-xl bg-warning-soft px-4 py-3 text-[13px] text-warning sm:flex-row sm:items-center sm:justify-between">
                  <span className="flex items-start gap-2">
                    <CpuIcon className="mt-0.5 size-4 shrink-0" />
                    This project has no model provider yet. {canAdmin ? "Start with the built-in mock, it needs no key." : "Ask a project admin to add one."}
                  </span>
                  {canAdmin && (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={addMock.isPending}
                      onClick={() =>
                        addMock.mutate(
                          { name: "mock", kind: "mock", is_default: true },
                          { onSuccess: () => toast.success("The built-in mock is ready."), onError: (err) => toast.error(errorMessage(err)) },
                        )
                      }
                    >
                      {addMock.isPending ? "Adding..." : "Use the built-in mock"}
                    </Button>
                  )}
                </div>
              )}
              <div className="space-y-1.5">
                <Label>Kinds of test</Label>
                <div className="grid gap-2 sm:grid-cols-2">
                  {(["unit", "edge", "negative", "api"] as TestKind[]).map((k) => {
                    const allowed = kindsAllowed.includes(k);
                    const on = kinds.includes(k);
                    return (
                      <button
                        key={k}
                        type="button"
                        role="checkbox"
                        aria-checked={on}
                        disabled={!allowed}
                        onClick={() => setKinds((cur) => (on ? cur.filter((x) => x !== k) : [...cur, k]))}
                        className={cn(
                          "flex items-start gap-2.5 rounded-xl bg-muted px-3 py-2.5 text-left transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50",
                          on && "bg-primary-soft hover:bg-primary-soft",
                        )}
                      >
                        <span className={cn("mt-0.5 flex size-4 shrink-0 items-center justify-center rounded ring-1 ring-input", on && "bg-primary text-primary-foreground ring-primary")}>
                          {on && <CheckIcon className="size-3" strokeWidth={3} />}
                        </span>
                        <span>
                          <span className="block text-[13px] font-medium">{TEST_KIND_LABEL[k]}</span>
                          <span className="block text-[12px] leading-snug text-muted-foreground">
                            {allowed ? TEST_KIND_DESCRIPTION[k] : k === "api" ? "Needs an OpenAPI document: start from API specs." : "API specs generate API tests only."}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
              {enabled.length > 1 && (
                <Field label="Model provider">
                  <SimpleSelect
                    aria-label="Model provider"
                    value={providerId}
                    onValueChange={setProviderId}
                    options={[{ value: "", label: "The project's default" }, ...enabled.map((p) => ({ value: p.id, label: `${p.name} (${p.model})` }))]}
                  />
                </Field>
              )}
              <Field label="Instructions" htmlFor="gen-instructions" hint="Optional. Anything the model should know, like a fixture to use or a rule the code follows.">
                <Textarea id="gen-instructions" maxLength={2000} rows={3} value={instructions} onChange={(e) => setInstructions(e.target.value)} />
              </Field>
              <p className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                Tests without a meaningful assertion are refused before you see them. <Hint term="refused" />
              </p>
              {error && <FieldError>{error}</FieldError>}
            </DialogBody>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={generate.isPending || noProvider}>
                <FlaskConicalIcon />
                {generate.isPending ? "Starting..." : "Generate tests"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** What a generation produced: proposed tests, and the refused ones with why. */
export function GenerationResult({ pid, generationId, onClose }: { pid: string; generationId: string; onClose: () => void }) {
  const q = useGeneration(pid, generationId);
  const refresh = useRefreshTests(pid);
  const g = q.data;
  const done = g && !inFlight(g.status);
  React.useEffect(() => {
    if (done) refresh();
    // refresh once when the generation settles
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [done]);

  return (
    <>
      <DialogBody className="space-y-4" aria-live="polite">
        {!g || inFlight(g.status) ? (
          <div className="flex items-center gap-3 rounded-xl bg-muted px-4 py-4 text-[13.5px]">
            <Loader2Icon className="size-4 animate-spin text-primary" />
            The model is writing tests from the analyzed source. Each one is checked for a real assertion before it is kept.
          </div>
        ) : g.status === "failed" ? (
          <FieldError>{g.error ?? "The generation failed."} Check the model provider in Settings, then try again.</FieldError>
        ) : (
          <GenerationSummary g={g} />
        )}
        {q.isError && <FieldError>{errorMessage(q.error)}</FieldError>}
      </DialogBody>
      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
        {g?.status === "done" && g.accepted_count > 0 && (
          <Button nativeButton={false} render={<Link href={`/projects/${pid}/tests?generation=${g.id}&status=proposed`} onClick={onClose} />}>
            Review {plural(g.accepted_count, "test")}
          </Button>
        )}
      </DialogFooter>
    </>
  );
}

export function GenerationSummary({ g }: { g: Generation }) {
  return (
    <div className="space-y-4" data-qa="generation-result">
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl bg-savings-soft px-4 py-3">
          <div className="tabular text-[22px] font-semibold text-savings" data-qa="proposed-count">
            {g.accepted_count}
          </div>
          <div className="text-[12.5px] text-savings">{g.accepted_count === 1 ? "test proposed" : "tests proposed"} for review</div>
        </div>
        <div className="rounded-xl bg-ember-soft px-4 py-3">
          <div className="tabular text-[22px] font-semibold text-ember" data-qa="refused-count">
            {g.rejected_count}
          </div>
          <div className="text-[12.5px] text-ember">refused: no meaningful assertion</div>
        </div>
      </div>
      {g.rejections.length > 0 && (
        <div>
          <h3 className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold">
            Refused before you saw them <Hint term="refused" />
          </h3>
          <ul className="space-y-1.5" data-qa="rejections">
            {g.rejections.map((r, i) => (
              <li key={`${r.name}-${i}`} className="flex items-start gap-2.5 rounded-lg bg-muted px-3 py-2 text-[12.5px]">
                <BanIcon className="mt-0.5 size-3.5 shrink-0 text-ember" aria-hidden />
                <span className="min-w-0">
                  <span className="font-mono font-medium break-all">{r.name}</span>
                  <span className="block text-muted-foreground">{r.reason}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {g.operations_covered.length > 0 && (
        <p className="text-[12.5px] text-muted-foreground">
          Covers {plural(g.operations_covered.length, "operation")}: <span className="font-mono">{g.operations_covered.join(", ")}</span>
        </p>
      )}
      <p className="text-[12px] text-subtle">
        {g.provider_kind} model {g.model}, {formatDuration(g.model_ms)} of model time, {g.input_tokens + g.output_tokens} tokens.
      </p>
    </div>
  );
}
