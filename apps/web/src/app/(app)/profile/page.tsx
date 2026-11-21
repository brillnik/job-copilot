import type { Metadata } from "next";
import { ProfileView } from "@/features/profile/profile-view";

export const metadata: Metadata = { title: "Profile · Job Copilot" };

export default function Page() {
  return <ProfileView />;
}
