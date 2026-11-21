export type Theme = "light" | "dark" | "system";
export const THEMES: readonly Theme[] = ["light", "dark", "system"];

// The ONLY thing kept in localStorage: the last theme choice (non-sensitive),
// so the first paint is right before settings load. Never tokens.
export const THEME_STORAGE_KEY = "jc-theme";

export function isTheme(value: unknown): value is Theme {
  return value === "light" || value === "dark" || value === "system";
}

export function readStoredTheme(): Theme {
  try {
    const v = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(v) ? v : "system";
  } catch {
    return "system";
  }
}

export function storeTheme(theme: Theme) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    /* private mode / blocked storage: theme just won't persist locally */
  }
}

export function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function applyTheme(theme: Theme) {
  const dark = theme === "dark" || (theme === "system" && systemPrefersDark());
  const root = document.documentElement;
  root.classList.toggle("dark", dark);
  root.dataset.theme = theme;
}

// Runs before first paint (inlined in <head>) to avoid a light/dark flash.
export const noFlashScript = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});var d=t==="dark"||((t===null||t==="system")&&window.matchMedia("(prefers-color-scheme: dark)").matches);var r=document.documentElement;if(d)r.classList.add("dark");r.dataset.theme=t==="light"||t==="dark"?t:"system"}catch(e){}})()`;
