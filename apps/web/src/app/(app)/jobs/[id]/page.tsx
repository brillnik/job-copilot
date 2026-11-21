import type { Metadata } from "next";
import { Suspense } from "react";
import { JobDetailScreen } from "@/features/jobs/job-detail";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "Job · Job Copilot" };

async function Detail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <JobDetailScreen jobId={id} />;
}

// params is runtime data: it is read inside <Suspense> so the shell can prerender.
export default function Page(props: { params: Promise<{ id: string }> }) {
  return (
    <Suspense
      fallback={
        <SkeletonGroup label="Loading the job">
          <Skeleton className="h-64 w-full" />
        </SkeletonGroup>
      }
    >
      <Detail params={props.params} />
    </Suspense>
  );
}
