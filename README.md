# Job Copilot

- `apps/web` — Next.js (TypeScript, Tailwind, App Router)
- `apps/api` — FastAPI (managed with uv)

## Setup
```
bun install
cd apps/api && uv sync
cp apps/api/.env.example apps/api/.env; cp apps/web/.env.example apps/web/.env.local
```

## Commands
- `bun dev` — run both (web :3000, api :8000, docs :8000/docs)
- `bun test` is bun's own runner, so use `bun run test` / `bun run lint` / `bun run build`
