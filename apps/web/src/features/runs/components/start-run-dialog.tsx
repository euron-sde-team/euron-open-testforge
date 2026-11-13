"use client";

import { ShieldCheckIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldError } from "@/components/ui/label";
import { errorMessage } from "@/lib/api/errors";
import type { RunKind } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { RUN_KIND_DESCRIPTION, RUN_KIND_LABEL } from "@/lib/status";

import { useStartRun } from "../api";

const KINDS: RunKind[] = ["generated", "project", "all"];

/** Start a run in the sandbox, then follow it on its own page. */
export function StartRunDialog({
  pid,
  open,
  onOpenChange,
  testIds,
}: {
  pid: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Run only these generated tests (a test's "Run this test"). */
  testIds?: string[];
}) {
  const start = useStartRun(pid);
  const router = useRouter();
  const [kind, setKind] = React.useState<RunKind>("generated");
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (open) {
      setKind("generated");
      setError(null);
    }
  }, [open]);

  function submit() {
    setError(null);
    start.mutate(testIds?.length ? { kind: "generated", test_ids: testIds } : { kind }, {
      onSuccess: (run) => {
        onOpenChange(false);
        router.push(`/projects/${pid}/runs/${run.id}`);
      },
      onError: (err) => setError(errorMessage(err)),
    });
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !start.isPending && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{testIds?.length ? "Run this test" : "Start a run"}</DialogTitle>
          <DialogDescription>The run uses the project&apos;s current code and its run limits.</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          {!testIds?.length && (
            <div role="radiogroup" aria-label="What to run" className="grid gap-2">
              {KINDS.map((k) => (
                <button
                  key={k}
                  type="button"
                  role="radio"
                  aria-checked={kind === k}
                  onClick={() => setKind(k)}
                  className={cn(
                    "rounded-xl bg-muted px-4 py-3 text-left transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring",
                    kind === k && "bg-primary-soft ring-2 ring-primary/40 hover:bg-primary-soft",
                  )}
                >
                  <span className="block text-[13.5px] font-medium">{RUN_KIND_LABEL[k]}</span>
                  <span className="block text-[12.5px] text-muted-foreground">{RUN_KIND_DESCRIPTION[k]}</span>
                </button>
              ))}
            </div>
          )}
          <p className="flex items-start gap-2.5 rounded-xl bg-savings-soft px-3.5 py-3 text-[12.5px] leading-relaxed text-savings">
            <ShieldCheckIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
            It runs in the sandbox: no network, no credentials, only this run&apos;s files, and fixed CPU, memory, output and time limits.
          </p>
          {error && <FieldError>{error}</FieldError>}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={start.isPending}>
            {start.isPending ? "Starting..." : "Run in the sandbox"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
