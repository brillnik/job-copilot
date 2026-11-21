import type { Metadata } from "next";
import { PageHeader } from "@/components/shell/page-header";
import { DigestView } from "@/features/autopilot/digest-view";

export const metadata: Metadata = { title: "Daily digest · Job Copilot" };

export default function Page() {
  return (
    <>
      <PageHeader
        title="Daily digest"
        description="What Autopilot submitted, skipped and needs a person for."
      />
      <DigestView />
    </>
  );
}
