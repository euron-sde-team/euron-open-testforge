import type { Metadata } from "next";
import { Suspense } from "react";

import { SpecsScreen } from "@/features/specs/components/specs-screen";

export const metadata: Metadata = { title: "API specs" };

export default function Page() {
  return (
    <Suspense>
      <SpecsScreen />
    </Suspense>
  );
}
