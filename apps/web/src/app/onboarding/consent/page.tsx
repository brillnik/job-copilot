import type { Metadata } from "next";
import { ConsentStep } from "@/features/onboarding/consent-step";

export const metadata: Metadata = { title: "Consent · Job Copilot" };

export default function Page() {
  return <ConsentStep />;
}
