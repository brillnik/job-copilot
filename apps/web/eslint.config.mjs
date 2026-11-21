import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import jsxA11y from "eslint-plugin-jsx-a11y";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // eslint-config-next already registers the jsx-a11y plugin; turn on the
  // full recommended rule set on top of it.
  { rules: { ...jsxA11y.flatConfigs.recommended.rules } },
  globalIgnores([
    ".next*/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "storybook-static/**",
    "playwright-report/**",
    "test-results/**",
    "src/lib/api/schema.d.ts",
  ]),
]);

export default eslintConfig;
