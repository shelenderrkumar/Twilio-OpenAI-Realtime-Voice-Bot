"""Thin WebSocket client for the OpenAI Realtime API."""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import websockets

SendEvent = Callable[[dict[str, Any]], Awaitable[None]]

_HEADERS_KWARG = (
    "additional_headers" if int(websockets.__version__.split(".")[0]) >= 14 else "extra_headers"
)


@asynccontextmanager
async def connect_realtime(
    *, api_key: str, model: str, url: str
) -> AsyncIterator[tuple[SendEvent, AsyncIterator[dict[str, Any]]]]:
    """Open a Realtime session and yield ``(send_event, event_stream)``."""
    headers = {"Authorization": f"Bearer {api_key}", "OpenAI-Beta": "realtime=v1"}
    async with websockets.connect(f"{url}?model={model}", **{_HEADERS_KWARG: headers}) as ws:

        async def send_event(event: dict[str, Any]) -> None:
            await ws.send(json.dumps(event))

        async def event_stream() -> AsyncIterator[dict[str, Any]]:
            async for raw in ws:
                yield json.loads(raw)

        yield send_event, event_stream()
