"use client";

import { useEffect, useRef } from "react";
import { useSaveTheme, useSettings } from "@/hooks/use-settings";
import { useTheme } from "./theme-provider";

/**
 * Keeps the theme and GET/PUT /settings in step. Rendered only inside the
 * authenticated shell, so signed-out screens just use the local choice.
 *  - Once settings load, a *configured* user's saved theme wins.
 *  - A local change is persisted with read-modify-write + If-Match.
 *  - Any failure is silent: the local choice keeps working.
 */
export function ThemeSync() {
  const { theme, adoptTheme } = useTheme();
  const settings = useSettings();
  const save = useSaveTheme();
  const synced = useRef(false);
  const lastSaved = useRef<string | null>(null);

  useEffect(() => {
    const prefs = settings.data;
    if (!prefs || synced.current) return;
    synced.current = true;
    lastSaved.current = prefs.preferences.theme;
    // Unconfigured users only have server defaults: keep the local pick and do
    // not PUT, which could mark onboarding as done.
    if (prefs.configured) adoptTheme(prefs.preferences.theme);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.data]);

  useEffect(() => {
    if (
      !synced.current ||
      !settings.data?.configured ||
      lastSaved.current === theme
    )
      return;
    lastSaved.current = theme;
    save.mutate(theme);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);

  return null;
}
