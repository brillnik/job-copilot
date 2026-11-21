import { existsSync } from "node:fs";

// e2e drives the user's installed Google Chrome (channel "chrome"); we never
// download browsers. If Chrome isn't installed the suite skips instead of failing.
const CANDIDATES = [
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome",
  "/usr/bin/google-chrome-stable",
  "/opt/google/chrome/chrome",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
];

export const hasChrome = CANDIDATES.some((p) => existsSync(p));
