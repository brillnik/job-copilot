"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
} from "react";
import {
  applyTheme,
  readStoredTheme,
  storeTheme,
  type Theme,
} from "@/lib/theme";

// Tiny external store so server render ("system") and client (localStorage)
// reconcile without setState-in-effect. The inline <head> script already put
// the right class on <html>, so there is no visual flash either way.
let current: Theme | null = null;
const listeners = new Set<() => void>();
const getTheme = (): Theme => (current ??= readStoredTheme());
const subscribeTheme = (cb: () => void) => {
  listeners.add(cb);
  return () => listeners.delete(cb);
};
function writeTheme(t: Theme) {
  current = t;
  storeTheme(t);
  listeners.forEach((l) => l());
}
/** Test helper: forget the cached choice. */
export function resetThemeStoreForTests() {
  current = null;
  listeners.forEach((l) => l());
}

const DARK_QUERY = "(prefers-color-scheme: dark)";
const subscribeDark = (cb: () => void) => {
  const mq = window.matchMedia(DARK_QUERY);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
};
const getDark = () => window.matchMedia(DARK_QUERY).matches;

type ThemeContextValue = {
  /** The user's choice: light | dark | system. */
  theme: Theme;
  /** What is actually showing. */
  resolved: "light" | "dark";
  /** Apply immediately and remember locally. Persisting to the API is done by ThemeSync. */
  setTheme: (theme: Theme) => void;
  /** Adopt a value coming from the server. */
  adoptTheme: (theme: Theme) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useSyncExternalStore(
    subscribeTheme,
    getTheme,
    () => "system" as Theme,
  );
  const systemDark = useSyncExternalStore(subscribeDark, getDark, () => false);
  const resolved: "light" | "dark" =
    theme === "dark" || (theme === "system" && systemDark) ? "dark" : "light";

  useEffect(() => {
    applyTheme(theme);
  }, [theme, systemDark]);

  const setTheme = useCallback((t: Theme) => writeTheme(t), []);
  const value = useMemo(
    () => ({ theme, resolved, setTheme, adoptTheme: setTheme }),
    [theme, resolved, setTheme],
  );
  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>");
  return ctx;
}
