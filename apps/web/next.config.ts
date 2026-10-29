import { existsSync } from "node:fs";
import { resolve } from "node:path";
import type { NextConfig } from "next";

// Env lives in the repo root. APP_ENV (local | dev | prod) selects
// .env.<APP_ENV>, layered over the shared .env. Existing process env wins.
const root = resolve(__dirname, "../..");
const appEnv = process.env.APP_ENV ?? "local";
for (const file of [`.env.${appEnv}`, ".env"]) {
  const path = resolve(root, file);
  if (existsSync(path)) process.loadEnvFile(path);
}

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
