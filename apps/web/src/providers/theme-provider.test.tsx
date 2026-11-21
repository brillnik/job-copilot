import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { THEME_STORAGE_KEY } from "@/lib/theme";
import {
  resetThemeStoreForTests,
  ThemeProvider,
  useTheme,
} from "./theme-provider";

function Probe() {
  const { theme, resolved, setTheme } = useTheme();
  return (
    <div>
      <p data-testid="v">
        {theme}/{resolved}
      </p>
      <button onClick={() => setTheme("dark")}>dark</button>
      <button onClick={() => setTheme("light")}>light</button>
    </div>
  );
}

afterEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  act(() => resetThemeStoreForTests());
});

describe("ThemeProvider", () => {
  it("restores the last choice from localStorage", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    act(() => resetThemeStoreForTests());
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("v")).toHaveTextContent("dark/dark");
    expect(document.documentElement).toHaveClass("dark");
  });

  it("switching toggles the .dark class and stores only the theme name", async () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    await userEvent.click(screen.getByText("dark"));
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    await userEvent.click(screen.getByText("light"));
    expect(document.documentElement).not.toHaveClass("dark");
    expect(Object.keys(localStorage)).toEqual([THEME_STORAGE_KEY]);
  });
});
