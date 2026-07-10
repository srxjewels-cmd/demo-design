"""In-process SSE broadcaster — pushes dashboard updates to open connections."""

import asyncio
import json

_subscribers: set[asyncio.Queue] = set()


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def broadcast(event_type: str, data: dict) -> None:
    payload = json.dumps({"type": event_type, "data": data}, default=str)
    for q in list(_subscribers):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            _subscribers.discard(q)
