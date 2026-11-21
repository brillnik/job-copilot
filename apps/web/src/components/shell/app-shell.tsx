"use client";

import { ErrorBoundary } from "@/components/error-boundary";
import { ThemeSync } from "@/providers/theme-sync";
import { Sidebar } from "./sidebar";
import { TabBar } from "./tab-bar";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh">
      <ThemeSync />
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-control focus:bg-surface focus:px-3 focus:py-2 focus:font-medium"
      >
        Skip to content
      </a>
      <Sidebar />
      <main
        id="main"
        className="min-w-0 flex-1 px-4 pt-6 pb-24 md:px-8 md:pt-8 md:pb-10"
      >
        <div className="mx-auto w-full max-w-[1200px]">
          <ErrorBoundary>{children}</ErrorBoundary>
        </div>
      </main>
      <TabBar />
    </div>
  );
}
