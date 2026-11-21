import {
  InboxIcon,
  ProfileIcon,
  ReviewIcon,
  SettingsIcon,
  SparkIcon,
  TrackerIcon,
} from "@/components/ui/icons";

export type NavItem = {
  href: string;
  label: string;
  Icon: typeof InboxIcon;
  /** Shows the review-queue count badge. */
  badge?: "review";
  /** Present in the mobile tab bar (5 tabs; "For you" is desktop-only). */
  tab: boolean;
};

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Inbox", Icon: InboxIcon, tab: true },
  { href: "/for-you", label: "For you", Icon: SparkIcon, tab: false },
  {
    href: "/review",
    label: "Review queue",
    Icon: ReviewIcon,
    badge: "review",
    tab: true,
  },
  { href: "/tracker", label: "Tracker", Icon: TrackerIcon, tab: true },
  {
    href: "/applications",
    label: "Applications",
    Icon: TrackerIcon,
    tab: false,
  },
  { href: "/autopilot", label: "Autopilot", Icon: SparkIcon, tab: false },
  { href: "/profile", label: "Profile", Icon: ProfileIcon, tab: true },
  {
    href: "/integrations",
    label: "Integrations",
    Icon: SettingsIcon,
    tab: false,
  },
  { href: "/settings", label: "Settings", Icon: SettingsIcon, tab: true },
];

// Mobile tab label is shorter: "Review" instead of "Review queue".
export const TAB_LABEL: Record<string, string> = { "/review": "Review" };

export function isActive(pathname: string, href: string) {
  return href === "/"
    ? pathname === "/"
    : pathname === href || pathname.startsWith(`${href}/`);
}
