import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ usePathname: () => "/tracker" }));
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...p
  }: {
    href: string;
    children: React.ReactNode;
  }) => (
    <a href={href} {...p}>
      {children}
    </a>
  ),
}));
vi.mock("@/hooks/use-me", () => ({
  useMe: () => ({ data: { name: "Asha", email: "a@x.io" } }),
}));
vi.mock("@/hooks/use-review-count", () => ({
  useReviewCount: () => ({ data: { count: 3, more: false } }),
}));

import { Sidebar } from "./sidebar";
import { TabBar } from "./tab-bar";

const wrap = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>,
  );

describe("navigation", () => {
  it("sidebar lists all six destinations, marks the current page and shows the review count", () => {
    wrap(<Sidebar />);
    const nav = screen.getByRole("navigation", { name: "Main" });
    for (const n of [
      "Inbox",
      "For you",
      "Review queue",
      "Tracker",
      "Profile",
      "Settings",
    ]) {
      expect(
        within(nav).getByRole("link", { name: new RegExp(n) }),
      ).toBeInTheDocument();
    }
    expect(within(nav).getByRole("link", { name: "Tracker" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      within(nav).getByRole("link", { name: /Review queue/ }),
    ).toHaveTextContent("3 awaiting review");
  });

  it("tab bar has the five mobile tabs (no For you)", () => {
    wrap(<TabBar />);
    const links = within(
      screen.getByRole("navigation", { name: "Main" }),
    ).getAllByRole("link");
    expect(
      links.map((l) =>
        l.textContent?.replace(/\d+ awaiting review|3/g, "").trim(),
      ),
    ).toEqual(["Inbox", "Review", "Tracker", "Profile", "Settings"]);
  });
});
