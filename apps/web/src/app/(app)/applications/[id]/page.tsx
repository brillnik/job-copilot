import type { Metadata } from "next";
import { PageHeader } from "@/components/shell/page-header";
import { ApplicationDetail } from "@/features/applications/application-detail";

export const metadata: Metadata = { title: "Application · Job Copilot" };

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <>
      <PageHeader title="Application" level="screen" />
      <ApplicationDetail id={id} />
    </>
  );
}
