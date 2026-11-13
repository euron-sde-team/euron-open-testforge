import type { Metadata } from "next";
import { Suspense } from "react";

import { SpecDetailScreen } from "@/features/specs/components/specs-screen";

export const metadata: Metadata = { title: "API spec" };

export default function Page() {
  return (
    <Suspense>
      <SpecDetailScreen />
    </Suspense>
  );
}
