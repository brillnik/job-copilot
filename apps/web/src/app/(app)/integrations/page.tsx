import type { Metadata } from "next";
import { PageHeader } from "@/components/shell/page-header";
import { IntegrationsPage } from "@/features/integrations/integrations-page";

export const metadata: Metadata = { title: "Integrations · Job Copilot" };

export default function Page() {
  return (
    <>
      <PageHeader
        title="Integrations"
        description="Saved answers, your browser extension, Gmail and data sharing."
      />
      <IntegrationsPage />
    </>
  );
}
