import type { Metadata } from "next";
import { Suspense } from "react";

import { TestDetailScreen } from "@/features/tests/components/test-detail-screen";

export const metadata: Metadata = { title: "Test" };

export default function Page() {
  return (
    <Suspense>
      <TestDetailScreen />
    </Suspense>
  );
}
