"use client";

import { useEffect, useRef, useState } from "react";
import {
  openEventStream,
  type SseMessage,
  type SseOptions,
  type SseStatus,
} from "@/lib/sse";

type Options = Pick<
  SseOptions,
  "isTerminal" | "lastEventId" | "backoffMs" | "fetchImpl"
> & {
  /** Pass null to stay disconnected (e.g. until a run id is known). */
  url: string | null;
  onMessage: (msg: SseMessage) => void;
};

/** Subscribe to an SSE endpoint for the lifetime of the component. */
export function useEventStream({
  url,
  onMessage,
  ...rest
}: Options): SseStatus {
  const [status, setStatus] = useState<SseStatus>("closed");
  const handler = useRef(onMessage);
  const restRef = useRef(rest);
  useEffect(() => {
    handler.current = onMessage;
    restRef.current = rest;
  });

  useEffect(() => {
    if (!url) return;
    return openEventStream({
      ...restRef.current,
      url,
      onMessage: (m) => handler.current(m),
      onStatus: setStatus,
    });
  }, [url]);

  return url ? status : "closed";
}
