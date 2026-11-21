import { vi } from "vitest";

// A scriptable stand-in for the openapi-fetch client, used by component tests:
//   vi.mock("@/lib/api/browser", async () => ({ api: (await import("@/features/common/fake-api")).fakeClient }));
// then set `routes["GET /autopilot"] = () => ({ body: {...} })` per test.

export type Handler = (args: { params?: unknown; body?: unknown }) => {
  status?: number;
  body?: unknown;
};

export const routes: Record<string, Handler> = {};
export const calls: Array<{ key: string; params?: unknown; body?: unknown }> =
  [];

export function resetApi() {
  for (const k of Object.keys(routes)) delete routes[k];
  calls.length = 0;
}

export const err = (status: number, code: string, message = code) => ({
  status,
  body: { code, message },
});

const call = (method: string) =>
  vi.fn(async (path: string, init?: { params?: unknown; body?: unknown }) => {
    const key = `${method} ${path}`;
    calls.push({ key, params: init?.params, body: init?.body });
    const h = routes[key];
    if (!h) throw new Error(`unstubbed ${key}`);
    const { status = 200, body } = h(init ?? {});
    const response = new Response(null, { status });
    return status >= 200 && status < 300
      ? { data: body, response }
      : { error: body, response };
  });

export const fakeClient = {
  GET: call("GET"),
  POST: call("POST"),
  PUT: call("PUT"),
  DELETE: call("DELETE"),
};

export function callsTo(key: string) {
  return calls.filter((c) => c.key === key);
}
