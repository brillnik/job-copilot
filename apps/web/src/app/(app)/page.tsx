import type { Metadata } from "next";
import { Inbox } from "@/features/jobs/inbox";

export const metadata: Metadata = { title: "Inbox · Job Copilot" };

export default function Page() {
  return <Inbox />;
}
