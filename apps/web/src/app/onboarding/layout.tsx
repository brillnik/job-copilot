import { OnboardingFrame } from "@/features/onboarding/onboarding-frame";

export default function OnboardingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <OnboardingFrame>{children}</OnboardingFrame>;
}
