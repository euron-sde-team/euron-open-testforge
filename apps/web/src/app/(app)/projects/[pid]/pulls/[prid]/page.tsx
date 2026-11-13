import type { Metadata } from "next";
import { Suspense } from "react";

import { PullDetailScreen } from "@/features/pulls/components/pulls-screen";

export const metadata: Metadata = { title: "Pull request" };

export default function Page() {
  return (
    <Suspense>
      <PullDetailScreen />
    </Suspense>
  );
}
