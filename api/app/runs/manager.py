from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict


class RunStreamManager:
    """In-memory SSE broker for run events."""

    def __init__(self) -> None:
        self._queues: Dict[str, asyncio.Queue[Any]] = {}
        self._history: Dict[str, list[Dict[str, Any]]] = {}

    def register(self, run_id: str) -> asyncio.Queue[Any]:
        queue = self._queues.get(run_id)
        if queue is None:
            queue = asyncio.Queue()
            self._queues[run_id] = queue
        self._history.setdefault(run_id, [])
        return queue

    def publish(self, run_id: str, event: str, payload: Dict[str, Any]) -> None:
        self._history.setdefault(run_id, []).append({"event": event, "data": payload})
        queue = self._queues.get(run_id)
        if queue:
            queue.put_nowait({"event": event, "data": payload})

    def close(self, run_id: str) -> None:
        queue = self._queues.pop(run_id, None)
        if queue:
            queue.put_nowait(None)

    async def stream(self, run_id: str) -> AsyncIterator[str]:
        history = list(self._history.get(run_id, []))
        for item in history:
            yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
        queue = self._queues.get(run_id)
        if queue is None:
            return
        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"


run_stream_manager = RunStreamManager()
