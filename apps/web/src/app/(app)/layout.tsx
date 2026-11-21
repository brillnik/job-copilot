import { AppShell } from "@/components/shell/app-shell";
import { SetupGate } from "@/features/onboarding/setup-gate";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <SetupGate>
      <AppShell>{children}</AppShell>
    </SetupGate>
  );
}
