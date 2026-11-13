import type { Metadata } from "next";
import { Suspense } from "react";

import { TestsScreen } from "@/features/tests/components/tests-screen";

export const metadata: Metadata = { title: "Tests" };

export default function Page() {
  return (
    <Suspense>
      <TestsScreen />
    </Suspense>
  );
}
