"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "@/components/brand/logo";
import { useMe } from "@/hooks/use-me";
import { cn } from "@/lib/cn";
import { isActive, NAV_ITEMS } from "./nav-items";
import { ReviewBadge } from "./review-badge";

export function Sidebar() {
  const pathname = usePathname();
  const me = useMe();
  return (
    <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-border bg-surface md:flex">
      <div className="flex items-center gap-2.5 px-5 py-5 text-[15px] font-semibold">
        <Logo />
        <span>Job Copilot</span>
      </div>
      <nav aria-label="Main" className="flex-1 px-3">
        <ul className="flex flex-col gap-0.5">
          {NAV_ITEMS.map(({ href, label, Icon, badge }) => {
            const active = isActive(pathname, href);
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex min-h-10 items-center gap-3 rounded-control px-3 text-body font-medium",
                    active
                      ? "bg-accent-soft text-accent-text"
                      : "text-muted hover:bg-surface-2 hover:text-text",
                  )}
                >
                  <Icon className="size-[18px]" />
                  <span className="flex-1">{label}</span>
                  {badge === "review" && <ReviewBadge />}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="border-t border-border px-5 py-4 text-hint">
        {me.data && (
          <p
            className="mb-2 truncate text-muted"
            title={me.data.email ?? undefined}
          >
            {me.data.name ?? me.data.email}
          </p>
        )}
        <a
          href="/auth/logout"
          className="font-medium text-accent-text underline underline-offset-2"
        >
          Sign out
        </a>
      </div>
    </aside>
  );
}
