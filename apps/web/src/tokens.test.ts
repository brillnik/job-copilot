import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");

function tokens(selector: ":root" | ".dark") {
  const body = css
    .split(new RegExp(`^${selector.replace(".", "\\.")} \\{`, "m"))[1]
    .split("}")[0];
  return Object.fromEntries(
    [...body.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6});/g)].map((m) => [
      m[1],
      m[2],
    ]),
  );
}

function lum(hex: string) {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = c.map((v) =>
    v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function ratio(a: string, b: string) {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

// [foreground, background, minimum ratio]: AA 4.5 for text, 3 for UI/focus.
const PAIRS: Array<[string, string, number]> = [
  ["text", "bg", 4.5],
  ["text", "surface", 4.5],
  ["text", "surface-2", 4.5],
  ["muted", "bg", 4.5],
  ["muted", "surface", 4.5],
  ["muted", "surface-2", 4.5],
  ["subtle", "bg", 4.5],
  ["subtle", "surface", 4.5],
  ["subtle", "surface-2", 4.5],
  ["on-accent", "accent", 4.5],
  ["on-accent", "accent-hover", 4.5],
  ["accent-text", "accent-soft", 4.5],
  ["accent-text", "surface", 4.5],
  ["accent-text", "bg", 4.5],
  ["ok", "ok-soft", 4.5],
  ["ok", "surface", 4.5],
  ["warn", "warn-soft", 4.5],
  ["warn", "surface", 4.5],
  ["bad", "bad-soft", 4.5],
  ["bad", "surface", 4.5],
  ["bad", "surface-2", 4.5],
  ["add-text", "add", 4.5],
  ["del-text", "del", 4.5],
  ["warn", "surface-2", 4.5],
  ["ok", "surface-2", 4.5],
  ["focus", "bg", 3],
  ["focus", "surface", 3],
  ["accent", "surface", 3],
  ["border-strong", "surface", 1.5],
];

describe.each([":root", ".dark"] as const)("colour tokens %s", (sel) => {
  const t = tokens(sel);
  it("defines the full token set", () => {
    for (const k of [
      "bg",
      "surface",
      "surface-2",
      "border",
      "border-strong",
      "text",
      "muted",
      "subtle",
      "accent",
      "accent-soft",
      "accent-text",
      "on-accent",
      "ok",
      "ok-soft",
      "warn",
      "warn-soft",
      "bad",
      "bad-soft",
      "add",
      "add-text",
      "del",
      "del-text",
      "focus",
    ]) {
      expect(t[k], k).toBeDefined();
    }
  });
  it.each(PAIRS)("%s on %s meets %s:1", (fg, bg, min) => {
    expect(ratio(t[fg], t[bg])).toBeGreaterThanOrEqual(min);
  });
});
