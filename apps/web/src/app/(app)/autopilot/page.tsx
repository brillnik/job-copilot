import type { Metadata } from "next";
import { PageHeader } from "@/components/shell/page-header";
import { AutopilotSettings } from "@/features/autopilot/autopilot-settings";

export const metadata: Metadata = { title: "Autopilot · Job Copilot" };

export default function Page() {
  return (
    <>
      <PageHeader
        title="Autopilot"
        description="Let Job Copilot apply to strong matches for you. It is off until you turn it on."
      />
      <AutopilotSettings />
    </>
  );
}
