import type { Metadata } from "next";
import { Suspense } from "react";

import { OverviewScreen } from "@/features/overview/components/overview-screen";

export const metadata: Metadata = { title: "Overview" };

export default function Page() {
  return (
    <Suspense>
      <OverviewScreen />
    </Suspense>
  );
}
