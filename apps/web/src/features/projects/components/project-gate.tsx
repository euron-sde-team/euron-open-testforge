"use client";

import { FolderSearchIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Surface } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import { useUiPrefs } from "@/lib/store";

import { useCurrentProject } from "../api";

/**
 * Every page inside /projects/<id>: remembers the project for next time, and says so
 * plainly when the project does not exist or is not shared with this person (the API
 * answers both with 404, so nobody learns which projects exist).
 */
export function ProjectGate({ children }: { children: React.ReactNode }) {
  const { pid, query } = useCurrentProject();
  const setLast = useUiPrefs((s) => s.setLastProject);

  React.useEffect(() => {
    if (query.data) setLast(pid);
  }, [pid, query.data, setLast]);

  if (query.isError && !query.data) {
    const missing = query.error instanceof ApiError && (query.error.status === 404 || query.error.status === 403);
    return (
      <Surface className="mt-6">
        {missing ? (
          <EmptyState
            icon={FolderSearchIcon}
            title="This project is not available"
            description="It may have been deleted, or it is not shared with you. Pick another project, or ask one of its admins to add you."
            action={
              <Button variant="outline" size="sm" nativeButton={false} render={<Link href="/projects" />}>
                See your projects
              </Button>
            }
          />
        ) : (
          <ErrorState error={query.error} title="Could not open this project" onRetry={() => void query.refetch()} />
        )}
      </Surface>
    );
  }
  return <>{children}</>;
}
