// SSE client with reconnect + Last-Event-ID.
//
// Why fetch instead of `new EventSource()`: the browser's EventSource cannot
// set a Last-Event-ID header on a *manual* reconnect, and it reconnects forever
// even after the server deliberately closed the stream (the backend closes
// after a terminal status). Reading the stream with fetch keeps the same wire
// protocol (id/event/data, `:` comment heartbeats) with full control over both.
// Cookies (Auth0 session) go to our same-origin /api proxy; no tokens here.

export type SseMessage<T = unknown> = {
  id: string | null;
  event: string;
  data: T;
  raw: string;
};

export type SseStatus = "connecting" | "open" | "reconnecting" | "closed";

export type SseOptions = {
  url: string;
  onMessage: (msg: SseMessage) => void;
  onStatus?: (status: SseStatus) => void;
  /** Return true to stop (e.g. a terminal status event). */
  isTerminal?: (msg: SseMessage) => boolean;
  lastEventId?: string | null;
  fetchImpl?: typeof fetch;
  /** Reconnect delays in ms; the last value repeats. */
  backoffMs?: number[];
  /** Treat the connection as dead if nothing (incl. heartbeats) arrives in this time. */
  idleTimeoutMs?: number;
};

const DEFAULT_BACKOFF = [1000, 2000, 5000, 10000];
// Server heartbeats every 15 s; allow two missed.
const DEFAULT_IDLE_MS = 35_000;

/** Incremental parser for the text/event-stream format. */
export function createSseParser(
  onEvent: (msg: SseMessage) => void,
  onId?: (id: string) => void,
) {
  let buffer = "";
  let id: string | null = null;
  let event = "";
  let data: string[] = [];

  function dispatch() {
    if (data.length === 0) {
      event = "";
      return;
    }
    const raw = data.join("\n");
    let parsed: unknown = raw;
    try {
      parsed = JSON.parse(raw);
    } catch {
      /* keep raw string */
    }
    onEvent({ id, event: event || "message", data: parsed, raw });
    event = "";
    data = [];
  }

  function line(l: string) {
    if (l === "") return dispatch();
    if (l.startsWith(":")) return; // comment / heartbeat
    const i = l.indexOf(":");
    const field = i === -1 ? l : l.slice(0, i);
    let value = i === -1 ? "" : l.slice(i + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "id") {
      id = value;
      onId?.(value);
    } else if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }

  return {
    push(chunk: string) {
      buffer += chunk;
      const lines = buffer.split(/\r\n|\n|\r/);
      buffer = lines.pop() ?? "";
      lines.forEach(line);
    },
  };
}

export function openEventStream(opts: SseOptions): () => void {
  const doFetch =
    opts.fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a));
  const backoff = opts.backoffMs ?? DEFAULT_BACKOFF;
  const idleMs = opts.idleTimeoutMs ?? DEFAULT_IDLE_MS;
  let lastId = opts.lastEventId ?? null;
  let stopped = false;
  let controller: AbortController | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let attempt = 0;

  const setStatus = (s: SseStatus) => opts.onStatus?.(s);

  function stop() {
    stopped = true;
    clearTimeout(timer);
    controller?.abort();
    setStatus("closed");
  }

  async function connect() {
    if (stopped) return;
    controller = new AbortController();
    const ac = controller;
    let idle: ReturnType<typeof setTimeout> | undefined;
    const arm = () => {
      clearTimeout(idle);
      idle = setTimeout(() => ac.abort(), idleMs);
    };
    setStatus(attempt === 0 ? "connecting" : "reconnecting");
    try {
      const headers: Record<string, string> = { Accept: "text/event-stream" };
      if (lastId) headers["Last-Event-ID"] = lastId;
      const res = await doFetch(opts.url, {
        headers,
        credentials: "include",
        cache: "no-store",
        signal: ac.signal,
      });
      if (res.status === 401 || res.status === 403 || res.status === 404) {
        // Not recoverable by retrying.
        stop();
        return;
      }
      if (!res.ok || !res.body) throw new Error(`stream status ${res.status}`);
      attempt = 0;
      setStatus("open");
      arm();
      const parser = createSseParser(
        (msg) => {
          opts.onMessage(msg);
          if (opts.isTerminal?.(msg)) stop();
        },
        (id) => {
          lastId = id;
        },
      );
      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
      for (;;) {
        const { done, value } = await reader.read();
        if (done || stopped) break;
        arm();
        parser.push(value);
      }
      clearTimeout(idle);
      if (stopped) return;
      // Server closed without a terminal event: treat as a drop and reconnect.
    } catch {
      clearTimeout(idle);
      if (stopped) return;
    }
    if (stopped) return;
    const delay = backoff[Math.min(attempt, backoff.length - 1)];
    attempt += 1;
    setStatus("reconnecting");
    timer = setTimeout(connect, delay);
  }

  void connect();
  return stop;
}
