import { redirect } from "next/navigation";

// The Inbox lives at "/" (the app's home); /inbox is an alias.
export default function InboxAlias() {
  redirect("/");
}
