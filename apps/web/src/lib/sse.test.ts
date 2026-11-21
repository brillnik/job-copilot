import { describe, expect, it, vi } from "vitest";
import { createSseParser, openEventStream, type SseMessage } from "./sse";

function streamOf(chunks: string[]) {
  const enc = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(c) {
      chunks.forEach((x) => c.enqueue(enc.encode(x)));
      c.close();
    },
  });
}

describe("createSseParser", () => {
  it("parses id/event/data, ignores heartbeat comments, handles split chunks", () => {
    const got: SseMessage[] = [];
    const p = createSseParser((m) => got.push(m));
    p.push(": keep-alive\n\nid: 7\nevent: step\nda");
    p.push('ta: {"seq":1,"type":"step"}\n\n');
    expect(got).toHaveLength(1);
    expect(got[0]).toMatchObject({
      id: "7",
      event: "step",
      data: { seq: 1, type: "step" },
    });
  });
});

describe("openEventStream", () => {
  it("reconnects with Last-Event-ID after a drop and stops at a terminal event", async () => {
    const calls: Array<Record<string, string>> = [];
    const fetchImpl = vi.fn(async (_u: unknown, init?: RequestInit) => {
      calls.push({ ...(init?.headers as Record<string, string>) });
      const n = calls.length;
      return new Response(
        streamOf(
          n === 1
            ? ['id: 1\nevent: step\ndata: {"seq":1}\n\n']
            : ['id: 2\nevent: status\ndata: {"seq":2,"type":"done"}\n\n'],
        ),
        { status: 200 },
      );
    }) as unknown as typeof fetch;

    const seen: string[] = [];
    await new Promise<void>((resolve) => {
      openEventStream({
        url: "/api/runs/r1/events",
        fetchImpl,
        backoffMs: [1],
        onMessage: (m) => seen.push(m.id ?? ""),
        isTerminal: (m) => (m.data as { type?: string }).type === "done",
        onStatus: (s) => s === "closed" && resolve(),
      });
    });
    expect(seen).toEqual(["1", "2"]);
    expect(calls[0]["Last-Event-ID"]).toBeUndefined();
    expect(calls[1]["Last-Event-ID"]).toBe("1");
  });

  it("stops on 401 without retrying", async () => {
    const fetchImpl = vi.fn(
      async () => new Response("", { status: 401 }),
    ) as unknown as typeof fetch;
    await new Promise<void>((resolve) => {
      openEventStream({
        url: "/x",
        fetchImpl,
        onMessage: () => {},
        onStatus: (s) => s === "closed" && resolve(),
      });
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
