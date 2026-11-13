import type { Metadata } from "next";
import { Suspense } from "react";

import { RunDetailScreen } from "@/features/runs/components/run-detail-screen";

export const metadata: Metadata = { title: "Run" };

export default function Page() {
  return (
    <Suspense>
      <RunDetailScreen />
    </Suspense>
  );
}
