import type { Metadata } from "next";
import { PageHeader } from "@/components/shell/page-header";
import { ApplyRun } from "@/features/applications/apply-run";

export const metadata: Metadata = { title: "Apply · Job Copilot" };

export default async function Page({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  return (
    <>
      <PageHeader title="Apply" level="screen" />
      <ApplyRun runId={runId} />
    </>
  );
}
