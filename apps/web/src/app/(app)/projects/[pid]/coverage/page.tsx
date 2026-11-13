import type { Metadata } from "next";
import { Suspense } from "react";

import { CoverageScreen } from "@/features/coverage/components/coverage-screen";

export const metadata: Metadata = { title: "Coverage" };

export default function Page() {
  return (
    <Suspense>
      <CoverageScreen />
    </Suspense>
  );
}
