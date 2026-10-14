import asyncio
import json

from langchain_core.tools import tool

from voicebot.realtime.executor import ToolExecutor


@tool
async def slow_echo(text: str) -> str:
    """Echo after a delay."""
    await asyncio.sleep(0.05)
    return text


@tool
def fast_echo(text: str) -> str:
    """Echo immediately."""
    return text


@tool
def broken() -> str:
    """Always fails."""
    raise RuntimeError("database down")


def call(name, arguments, call_id="c1"):
    return {"name": name, "arguments": arguments, "call_id": call_id}


def output_of(event):
    assert event["type"] == "conversation.item.create"
    return event["item"]["output"]


async def test_successful_call():
    name, event = await ToolExecutor([fast_echo]).run_call(call("fast_echo", '{"text": "hi"}'))
    assert name == "fast_echo"
    assert json.loads(output_of(event)) == {"tool_output": "hi"}
    assert event["item"]["call_id"] == "c1"


async def test_errors_are_reported_to_the_model_not_raised():
    executor = ToolExecutor([broken, fast_echo])
    _, unknown = await executor.run_call(call("missing", "{}"))
    _, bad_json = await executor.run_call(call("fast_echo", "{not json"))
    _, failure = await executor.run_call(call("broken", "{}"))
    assert "unknown tool" in output_of(unknown)
    assert "valid JSON" in output_of(bad_json)
    assert "database down" in output_of(failure)


async def test_concurrent_calls_complete_in_finish_order():
    executor = ToolExecutor([slow_echo, fast_echo])
    executor.submit(call("slow_echo", '{"text": "slow"}', "1"))
    executor.submit(call("fast_echo", '{"text": "fast"}', "2"))  # no "already in progress" error
    outputs = executor.outputs()
    first = await anext(outputs)
    second = await anext(outputs)
    await outputs.aclose()
    assert [first[0], second[0]] == ["fast_echo", "slow_echo"]
