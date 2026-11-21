import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader } from "@/components/shell/page-header";
import { ForYou } from "@/features/recommendations/for-you";

export const metadata: Metadata = { title: "For you · Job Copilot" };

export default function Page() {
  return (
    <>
      <PageHeader
        title="For you"
        description="Today's roles, picked from your profile and preferences."
        actions={
          <Link
            href="/autopilot"
            className="inline-flex min-h-11 items-center text-accent-text underline underline-offset-2"
          >
            Autopilot
          </Link>
        }
      />
      <ForYou />
    </>
  );
}
