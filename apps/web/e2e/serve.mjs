// Starts `next dev` on the given port for the e2e web servers and restarts it
// once if it exits early. Some Next.js versions stop `next dev` on every other
// start to show a "security upgrade" notice ("Retry the same command"), which
// would otherwise make every second e2e run fail with ERR_CONNECTION_REFUSED.
import { spawn } from "node:child_process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const next = require.resolve("next/dist/bin/next");
const port = process.argv[2] ?? "3100";
let child;
let stopping = false;

function start(attempt) {
  const startedAt = Date.now();
  child = spawn(process.execPath, [next, "dev", "-p", port], {
    stdio: "inherit",
    env: process.env,
  });
  child.on("exit", (code) => {
    if (stopping) process.exit(0);
    if (attempt < 3 && Date.now() - startedAt < 20_000)
      return start(attempt + 1);
    process.exit(code ?? 1);
  });
}
for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => {
    stopping = true;
    child?.kill(sig);
    setTimeout(() => process.exit(0), 3000).unref();
  });
}
start(0);
