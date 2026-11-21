// Minimal static file server for the built Storybook (no extra dependency).
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, resolve } from "node:path";

const root = resolve(process.argv[2] ?? "storybook-static");
const port = Number(process.argv[3] ?? 6007);
const types = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

createServer((req, res) => {
  const path = normalize(
    decodeURIComponent(new URL(req.url, "http://x").pathname),
  ).replace(/^(\.\.[/\\])+/, "");
  let file = join(root, path);
  if (existsSync(file) && statSync(file).isDirectory())
    file = join(file, "index.html");
  if (!file.startsWith(root) || !existsSync(file)) {
    res.writeHead(404).end("not found");
    return;
  }
  res.writeHead(200, {
    "content-type": types[extname(file)] ?? "application/octet-stream",
  });
  createReadStream(file).pipe(res);
}).listen(port, () => console.log(`storybook-static on :${port}`));
