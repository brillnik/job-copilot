import { defineConfig } from "@playwright/test";
import { hasChrome } from "./e2e/chrome";

// Storybook 10 needs Node >= 22.12 (or 20.19+); skip the stories project otherwise.
const [major, minor] = process.versions.node.split(".").map(Number);
const storybookOk =
  major > 22 || (major === 22 && minor >= 12) || (major === 20 && minor >= 19);

// Ports can be overridden so parallel runs (e.g. two agents) do not collide.
const APP = process.env.E2E_APP_PORT ?? "3100";
const AUTH = process.env.E2E_AUTH_PORT ?? "3101";
const SB = process.env.E2E_SB_PORT ?? "6007";
const DIST = process.env.E2E_DIST_SUFFIX ?? "";

// Dummy Auth0 values: the SDK only needs them to construct; no network call is
// made for requests without a session. Real secrets are never used by e2e.
const dummyAuth0 = {
  AUTH0_DOMAIN: "e2e.invalid",
  AUTH0_CLIENT_ID: "e2e",
  AUTH0_CLIENT_SECRET: "e2e",
  AUTH0_SECRET: "e2e-e2e-e2e-e2e-e2e-e2e-e2e-e2e-e2e-e2e-e2e-e2e-0123456789",
  AUTH0_AUDIENCE: "https://e2e.invalid/api",
  APP_BASE_URL: `http://localhost:${APP}`,
};

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  // Retries absorb the occasional `next dev` restart (see e2e/serve.mjs).
  retries: 2,
  reporter: [["list"]],
  use: { channel: "chrome", trace: "retain-on-failure" },
  projects: [
    // Signed-in app: auth bypassed (E2E_STUB_AUTH) and /api/* stubbed in the browser.
    {
      name: "app",
      testMatch: /app\..*\.spec\.ts/,
      use: { baseURL: `http://localhost:${APP}` },
    },
    // Real middleware, no session: proves unauthenticated users are redirected.
    {
      name: "auth",
      testMatch: /auth\..*\.spec\.ts/,
      use: { baseURL: `http://localhost:${AUTH}` },
    },
    // Built Storybook, axe on every story in both themes.
    ...(storybookOk
      ? [
          {
            name: "stories",
            testMatch: /stories\..*\.spec\.ts/,
            use: { baseURL: `http://localhost:${SB}` },
          },
        ]
      : []),
  ],
  webServer: hasChrome
    ? [
        {
          command: `node e2e/serve.mjs ${APP}`,
          url: `http://localhost:${APP}/sign-in`,
          reuseExistingServer: false,
          gracefulShutdown: { signal: "SIGTERM", timeout: 5000 },
          timeout: 180_000,
          env: {
            ...dummyAuth0,
            E2E_STUB_AUTH: "1",
            NEXT_DIST_DIR: `.next-e2e${DIST}`,
            NEXT_TELEMETRY_DISABLED: "1",
          },
        },
        {
          command: `node e2e/serve.mjs ${AUTH}`,
          url: `http://localhost:${AUTH}/sign-in`,
          reuseExistingServer: false,
          gracefulShutdown: { signal: "SIGTERM", timeout: 5000 },
          timeout: 180_000,
          env: {
            ...dummyAuth0,
            APP_BASE_URL: `http://localhost:${AUTH}`,
            NEXT_DIST_DIR: `.next-e2e-auth${DIST}`,
            NEXT_TELEMETRY_DISABLED: "1",
          },
        },
        ...(storybookOk
          ? [
              {
                command: `bun run build-storybook && node e2e/static.mjs storybook-static ${SB}`,
                url: `http://localhost:${SB}/index.json`,
                reuseExistingServer: false,
                timeout: 300_000,
                env: { STORYBOOK_DISABLE_TELEMETRY: "1" },
              },
            ]
          : []),
      ]
    : undefined,
});
