import type { Metadata } from "next";
import { PreferencesStep } from "@/features/onboarding/preferences-step";

export const metadata: Metadata = { title: "Preferences · Job Copilot" };

export default function Page() {
  return <PreferencesStep />;
}
