import type { Metadata } from "next";
import { UploadStep } from "@/features/onboarding/upload-step";

export const metadata: Metadata = { title: "Upload your resume · Job Copilot" };

export default function Page() {
  return <UploadStep />;
}
