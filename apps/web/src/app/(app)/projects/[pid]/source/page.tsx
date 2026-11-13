import type { Metadata } from "next";
import { Suspense } from "react";

import { SourceScreen } from "@/features/source/components/source-screen";

export const metadata: Metadata = { title: "Source" };

export default function Page() {
  return (
    <Suspense>
      <SourceScreen />
    </Suspense>
  );
}
