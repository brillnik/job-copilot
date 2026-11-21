"""Server-sent events for one run: replay from a cursor, then follow the log.

The run's event log (run_events) is the source of truth, so a reconnecting client
loses nothing. The stream polls it; a Redis pub/sub wake-up (channel run:{id}) can
replace the sleep later without changing what is sent.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from app.services.run_state import TERMINAL


@dataclass
class Batch:
    events: list[tuple[int, str, dict, str]]  # (seq, type, payload, iso ts)
    status: str | None  # the run's status read after the events


def format_event(seq: int, type_: str, payload: dict, ts: str) -> str:
    data = json.dumps({"seq": seq, "type": type_, "payload": payload, "ts": ts})
    return f"id: {seq}\nevent: {type_}\ndata: {data}\n\n"


async def stream(
    fetch: Callable[[int], Awaitable[Batch]],
    after: int,
    *,
    poll_s: float,
    heartbeat_s: float,
    disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[str]:
    cursor, quiet = after, 0.0
    while True:
        batch = await fetch(cursor)
        for seq, type_, payload, ts in batch.events:
            yield format_event(seq, type_, payload, ts)
            cursor, quiet = seq, 0.0
        # Status is read after the events, so a terminal status with nothing left
        # to send means the client has seen everything.
        if not batch.events and (batch.status is None or batch.status in TERMINAL):
            return
        if await disconnected():
            return
        if batch.events:
            continue
        await asyncio.sleep(poll_s)
        quiet += poll_s
        if quiet >= heartbeat_s:
            yield ": heartbeat\n\n"
            quiet = 0.0
