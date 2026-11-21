import type { Metadata } from "next";
import { ReviewQueue } from "@/features/review/review-queue";

export const metadata: Metadata = { title: "Review queue · Job Copilot" };

export default function Page() {
  return <ReviewQueue />;
}
