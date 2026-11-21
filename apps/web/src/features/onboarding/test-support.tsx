import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

export const apiMock = {
  GET: vi.fn(),
  POST: vi.fn(),
  PUT: vi.fn(),
  DELETE: vi.fn(),
};
export const router = { push: vi.fn(), replace: vi.fn() };

export const ok = (data: unknown, headers: Record<string, string> = {}) => ({
  data,
  response: new Response(null, { status: 200, headers }),
});
export const fail = (status: number, body: unknown) => ({
  error: body,
  response: new Response(null, { status }),
});
export const notFound = () =>
  fail(404, { code: "not_found", message: "Not found" });

export function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return { client, ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>) };
}

export const profileOut = (over: Record<string, unknown> = {}) => ({
  id: "p1",
  status: "draft",
  version: null,
  resume_id: "r1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  approved_at: null,
  data: {
    contact: { name: "Asha Rao", email: "asha@example.com", phone: null, location: null, links: ["https://asha.dev"] },
    summary: null,
    experience: [
      {
        id: "e1",
        company: "Acme",
        title: "Engineer",
        location: null,
        start: "2020",
        end: null,
        bullets: [{ id: "b1", text: "Cut p95 latency by 40% using React" }],
      },
    ],
    projects: [],
    education: [],
    skills: ["React", "Go"],
  },
  ...over,
});
