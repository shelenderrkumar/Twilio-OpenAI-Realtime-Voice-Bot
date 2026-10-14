import asyncio
from collections.abc import AsyncIterator
from typing import TypeVar

T = TypeVar("T")


async def amerge(
    streams: dict[str, AsyncIterator[T]], *, stop_when_done: str | None = None
) -> AsyncIterator[tuple[str, T]]:
    """Interleave several async iterators, yielding ``(key, item)`` as items arrive.

    If ``stop_when_done`` names a stream, the merge ends as soon as that stream is
    exhausted (e.g. the caller hung up) instead of waiting for every stream to end.
    """
    pending: dict[asyncio.Task, str] = {
        asyncio.ensure_future(anext(stream)): key for key, stream in streams.items()
    }
    try:
        while pending:
            done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                key = pending.pop(task)
                try:
                    item = task.result()
                except StopAsyncIteration:
                    if key == stop_when_done:
                        return
                    continue
                yield key, item
                pending[asyncio.ensure_future(anext(streams[key]))] = key
    finally:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
