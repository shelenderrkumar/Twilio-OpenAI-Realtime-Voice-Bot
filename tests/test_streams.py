import asyncio

from voicebot.realtime.streams import amerge


async def items(*values, delay=0.0):
    for value in values:
        await asyncio.sleep(delay)
        yield value


async def forever():
    while True:
        await asyncio.sleep(3600)
        yield "never"


async def test_merges_all_streams():
    merged = [x async for x in amerge({"a": items(1, 2), "b": items(3)})]
    assert sorted(merged) == [("a", 1), ("a", 2), ("b", 3)]


async def test_stops_when_named_stream_ends():
    # The model stream never ends on its own; hanging up must still finish the call.
    merged = [
        x async for x in amerge({"input": items(1, 2), "model": forever()}, stop_when_done="input")
    ]
    assert merged == [("input", 1), ("input", 2)]
