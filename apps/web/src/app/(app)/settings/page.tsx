import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { SettingsPage } from "@/features/settings/settings-page";

export const metadata: Metadata = { title: "Settings · Job Copilot" };

async function Body({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  // ?delete=1 is where the re-login for "delete account" returns to.
  return <SettingsPage autoOpenDelete={sp.delete === "1"} />;
}

export default function Page({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  return (
    <>
      <nav aria-label="More settings" className="mb-4 flex flex-wrap gap-x-4">
        {[
          ["/autopilot", "Autopilot"],
          ["/applications", "Applications"],
          ["/integrations", "Integrations"],
        ].map(([href, label]) => (
          <Link
            key={href}
            href={href}
            className="inline-flex min-h-11 items-center text-accent-text underline underline-offset-2"
          >
            {label}
          </Link>
        ))}
      </nav>
      <Suspense fallback={<Skeleton className="h-96" />}>
        <Body searchParams={searchParams} />
      </Suspense>
    </>
  );
}
