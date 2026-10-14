"""Runs the model's function calls concurrently and streams their results back."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


def function_call_output(call_id: str, output: Any) -> dict[str, Any]:
    """Build the Realtime event that hands a tool result back to the model."""
    return {
        "type": "conversation.item.create",
        "item": {
            "type": "function_call_output",
            "call_id": call_id,
            "output": output if isinstance(output, str) else json.dumps(output, default=str),
        },
    }


class ToolExecutor:
    """Queue of pending tool calls; results are yielded as soon as each one finishes.

    Calls never raise into the audio loop: a bad tool name, malformed arguments or a
    tool exception is reported back to the model as an error string so it can recover
    conversationally instead of dropping the phone call.
    """

    def __init__(self, tools: list[BaseTool]):
        self.tools_by_name = {tool.name: tool for tool in tools}
        self._calls: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def submit(self, call: dict[str, Any]) -> None:
        """Enqueue a ``response.function_call_arguments.done`` event."""
        self._calls.put_nowait(call)

    async def run_call(self, call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        name = call.get("name", "")
        tool = self.tools_by_name.get(name)
        if tool is None:
            output: Any = f"Error: unknown tool '{name}'. Available: {sorted(self.tools_by_name)}"
        else:
            try:
                args = json.loads(call.get("arguments") or "{}")
                output = {"tool_output": await tool.ainvoke(args)}
            except json.JSONDecodeError:
                output = f"Error: arguments must be valid JSON, got {call.get('arguments')!r}"
            except Exception as exc:  # surfaced to the model, never crashes the call
                logger.exception("Tool %s failed", name)
                output = f"Error while running {name}: {exc}"
        logger.info("tool %s -> %s", name, output)
        return name, function_call_output(call["call_id"], output)

    async def outputs(self) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Yield ``(tool_name, output_event)`` pairs forever, in completion order."""
        running: set[asyncio.Task] = set()
        next_call = asyncio.ensure_future(self._calls.get())
        try:
            while True:
                done, _ = await asyncio.wait(
                    running | {next_call}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    if task is next_call:
                        running.add(asyncio.ensure_future(self.run_call(task.result())))
                        next_call = asyncio.ensure_future(self._calls.get())
                    else:
                        running.discard(task)
                        yield task.result()
        finally:
            for task in running | {next_call}:
                task.cancel()
