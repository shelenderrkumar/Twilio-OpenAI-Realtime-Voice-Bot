"""Speech-to-speech ReAct agent on top of the OpenAI Realtime API.

The agent multiplexes three asynchronous streams for the lifetime of a call:

* ``input``  - audio events from the caller (Twilio phone line or browser mic)
* ``model``  - server events from the Realtime API (audio, transcripts, tool calls)
* ``tools``  - results of tool calls that finished running

Audio is never decoded here: the caller's encoding (G.711 mu-law for telephony,
PCM16 for browsers) is negotiated with the model so payloads pass straight through.
"""

import logging
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Literal

from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from voicebot.realtime.client import connect_realtime
from voicebot.realtime.executor import ToolExecutor
from voicebot.realtime.streams import amerge

logger = logging.getLogger(__name__)

AudioFormat = Literal["g711_ulaw", "pcm16"]
Emit = Callable[[dict[str, Any]], Awaitable[None]]

# Server events forwarded unchanged to the transport layer.
FORWARDED_EVENTS = {
    "response.audio.delta",
    "response.audio_transcript.delta",
    "response.audio_transcript.done",
    "input_audio_buffer.speech_started",
    "conversation.item.input_audio_transcription.completed",
}


def tool_definition(tool: BaseTool) -> dict[str, Any]:
    """Convert a LangChain tool into a Realtime ``session.tools`` entry."""
    function = convert_to_openai_tool(tool)["function"]
    return {"type": "function", **function}


class RealtimeVoiceAgent:
    def __init__(
        self,
        *,
        api_key: str,
        instructions: str,
        tools: list[BaseTool],
        model: str = "gpt-4o-realtime-preview",
        url: str = "wss://api.openai.com/v1/realtime",
        voice: str = "alloy",
        audio_format: AudioFormat = "g711_ulaw",
        max_conversation_items: int = 4,
        state_snapshot: Callable[[], Any] | None = None,
        connect=connect_realtime,
    ):
        self.api_key = api_key
        self.instructions = instructions
        self.tools = tools
        self.model = model
        self.url = url
        self.voice = voice
        self.audio_format = audio_format
        self.max_conversation_items = max_conversation_items
        self.state_snapshot = state_snapshot
        self._connect = connect

    def session_config(self) -> dict[str, Any]:
        return {
            "type": "session.update",
            "session": {
                "instructions": self.instructions,
                "voice": self.voice,
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                },
                "input_audio_transcription": {"model": "whisper-1"},
                "input_audio_format": self.audio_format,
                "output_audio_format": self.audio_format,
                "tools": [tool_definition(t) for t in self.tools],
                "tool_choice": "auto",
            },
        }

    async def run(self, input_events: AsyncIterator[dict[str, Any]], emit: Emit) -> None:
        """Drive one conversation until the caller's input stream ends."""
        executor = ToolExecutor(self.tools)
        # Sliding window over audio items, so long calls keep a bounded context.
        audio_items: deque[str] = deque()

        async with self._connect(api_key=self.api_key, model=self.model, url=self.url) as (
            send,
            model_events,
        ):
            await send(self.session_config())

            async for source, event in amerge(
                {"input": input_events, "model": model_events, "tools": executor.outputs()},
                stop_when_done="input",
            ):
                if source == "input":
                    await send(event)

                elif source == "tools":
                    tool_name, output_event = event
                    await send(output_event)
                    await send({"type": "response.create"})
                    if self.state_snapshot is not None:
                        await emit(
                            {
                                "type": "tool_output",
                                "name": tool_name,
                                "data": self.state_snapshot(),
                            }
                        )

                else:
                    await self._handle_model_event(event, executor, audio_items, send, emit)

    async def _handle_model_event(self, event, executor, audio_items, send, emit) -> None:
        kind = event.get("type")

        if kind in FORWARDED_EVENTS:
            await emit(event)
            if kind == "conversation.item.input_audio_transcription.completed":
                logger.info("caller: %s", event.get("transcript", "").strip())
            elif kind == "response.audio_transcript.done":
                logger.info("agent: %s", event.get("transcript", "").strip())

        elif kind == "response.function_call_arguments.done":
            logger.info("tool call %s(%s)", event.get("name"), event.get("arguments"))
            executor.submit(event)

        elif kind == "conversation.item.created":
            item = event.get("item") or {}
            if any(p.get("type") in ("audio", "input_audio") for p in item.get("content") or []):
                audio_items.append(item["id"])
            while len(audio_items) > self.max_conversation_items:
                await send({"type": "conversation.item.delete", "item_id": audio_items.popleft()})

        elif kind == "response.done":
            usage = (event.get("response") or {}).get("usage")
            if usage:
                logger.info("usage: %s", usage)

        elif kind == "error":
            logger.error("realtime error: %s", event.get("error"))
