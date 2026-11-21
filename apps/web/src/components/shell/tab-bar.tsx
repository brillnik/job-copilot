"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import { isActive, NAV_ITEMS, TAB_LABEL } from "./nav-items";
import { ReviewBadge } from "./review-badge";

/** Bottom tab bar for < 768px: Inbox, Review, Tracker, Profile, Settings. */
export function TabBar() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      <ul className="grid grid-cols-5">
        {NAV_ITEMS.filter((i) => i.tab).map(({ href, label, Icon, badge }) => {
          const active = isActive(pathname, href);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11.5px] font-medium",
                  active ? "text-accent-text" : "text-muted",
                )}
              >
                <span className="relative">
                  <Icon className="size-5" />
                  {badge === "review" && (
                    <ReviewBadge className="absolute -top-2 left-3" />
                  )}
                </span>
                {TAB_LABEL[href] ?? label}
                {active && (
                  <span
                    aria-hidden="true"
                    className="absolute top-0 h-0.5 w-8 rounded-full bg-accent"
                  />
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
