import Link from "next/link";
import { GmailSection } from "@/features/gmail/gmail-section";
import { ScreeningAnswers } from "@/features/screening/screening-answers";
import { ExtensionSection } from "./extension-section";
import { TrainingConsent } from "./training-consent";

const SECTIONS = [
  { href: "#screening-h", label: "Screening answers" },
  { href: "#extension", label: "Browser extension" },
  { href: "#gmail-h", label: "Gmail" },
  { href: "#train-h", label: "Training data" },
];

export function IntegrationsPage() {
  return (
    <div className="space-y-8">
      <nav aria-label="On this page" className="flex flex-wrap gap-x-4 gap-y-1">
        {SECTIONS.map((s) => (
          <Link
            key={s.href}
            href={s.href}
            className="inline-flex min-h-11 items-center text-accent-text underline underline-offset-2 md:min-h-8"
          >
            {s.label}
          </Link>
        ))}
      </nav>
      <ScreeningAnswers />
      <ExtensionSection />
      <GmailSection />
      <TrainingConsent />
    </div>
  );
}
