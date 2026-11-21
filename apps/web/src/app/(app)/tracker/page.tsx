import type { Metadata } from "next";
import { TrackerBoard } from "@/features/tracker/tracker-board";

export const metadata: Metadata = { title: "Tracker · Job Copilot" };

export default function Page() {
  return <TrackerBoard />;
}
