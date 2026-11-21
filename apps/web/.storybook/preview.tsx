import type { Decorator, Preview } from "@storybook/nextjs-vite";
import "../src/app/globals.css";

// Font variables normally come from next/font in the root layout.
const fontVars = {
  "--font-inter": "Inter, system-ui, sans-serif",
  "--font-jetbrains-mono": '"JetBrains Mono", ui-monospace, monospace',
} as React.CSSProperties;

const withTheme: Decorator = (Story, ctx) => {
  const theme = (ctx.globals.theme as "light" | "dark") ?? "light";
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.classList.add("font-sans");
  return (
    <div style={fontVars} className="min-h-24 bg-bg p-6 text-text">
      <Story />
    </div>
  );
};

const preview: Preview = {
  decorators: [withTheme],
  globalTypes: {
    theme: {
      description: "Colour theme",
      toolbar: {
        title: "Theme",
        icon: "circlehollow",
        items: [
          { value: "light", title: "Light" },
          { value: "dark", title: "Dark" },
        ],
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: { theme: "light" },
  parameters: {
    layout: "fullscreen",
    a11y: { test: "error" },
    viewport: {
      options: {
        mobile: {
          name: "Mobile 390",
          styles: { width: "390px", height: "844px" },
          type: "mobile",
        },
      },
    },
  },
};
export default preview;
