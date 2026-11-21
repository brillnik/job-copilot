import type { Metadata } from "next";
import { Suspense } from "react";
import { ReviewDetail } from "@/features/review/review-detail";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "Review draft · Job Copilot" };

async function Detail({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return <ReviewDetail runId={runId} />;
}

export default function Page({ params }: { params: Promise<{ runId: string }> }) {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <Detail params={params} />
    </Suspense>
  );
}
