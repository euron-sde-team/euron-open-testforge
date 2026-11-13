import type { Metadata } from "next";
import { Suspense } from "react";

import { PullsScreen } from "@/features/pulls/components/pulls-screen";

export const metadata: Metadata = { title: "Pull requests" };

export default function Page() {
  return (
    <Suspense>
      <PullsScreen />
    </Suspense>
  );
}
