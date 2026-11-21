import type { Metadata } from "next";
import { PageHeader } from "@/components/shell/page-header";
import { ApplicationList } from "@/features/applications/application-list";

export const metadata: Metadata = { title: "Applications · Job Copilot" };

export default function Page() {
  return (
    <>
      <PageHeader
        title="Applications"
        description="Every application Job Copilot has submitted, skipped or is working on."
      />
      <ApplicationList />
    </>
  );
}
