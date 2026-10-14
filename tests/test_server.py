import asyncio
import json
import threading
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from langchain_core.tools import tool
from pydantic import SecretStr

from voicebot.realtime import RealtimeVoiceAgent
from voicebot.server import create_app, realtime_to_twilio, twilio_to_realtime


@tool
def track_shipment(tracking_number: str) -> dict:
    """Look up a shipment."""
    return {"status": "ok", "shipment_status": f"{tracking_number} is out for delivery"}


class FakeRealtimeAPI:
    """Scripted stand-in for the OpenAI Realtime WebSocket.

    Caller audio -> the model asks for `track_shipment`; tool result -> the model speaks.
    """

    def __init__(self):
        self.received: list[dict] = []
        self.closed = threading.Event()  # set when the server tears the session down

    @asynccontextmanager
    async def connect(self, *, api_key, model, url):
        outbox: asyncio.Queue = asyncio.Queue()

        async def send(event):
            self.received.append(event)
            kind = event["type"]
            if kind == "input_audio_buffer.append" and event["audio"] == "caller-audio":
                await outbox.put({"type": "input_audio_buffer.speech_started"})
                await outbox.put(
                    {
                        "type": "response.function_call_arguments.done",
                        "name": "track_shipment",
                        "call_id": "call_1",
                        "arguments": '{"tracking_number": "397148"}',
                    }
                )
            elif kind == "response.create":
                await outbox.put({"type": "response.audio.delta", "delta": "agent-audio"})

        async def events():
            while True:
                yield await outbox.get()

        try:
            yield send, events()
        finally:
            self.closed.set()


def make_client(settings, fake: FakeRealtimeAPI, captured_formats: list):
    def agent_factory(audio_format):
        captured_formats.append(audio_format)
        return RealtimeVoiceAgent(
            api_key="test",
            instructions="Be helpful.",
            tools=[track_shipment],
            audio_format=audio_format,
            state_snapshot=lambda: ["snapshot"],
            connect=fake.connect,
        )

    return TestClient(create_app(settings, agent_factory=agent_factory))


def test_health_and_browser_page(settings):
    client = TestClient(create_app(settings, agent_factory=lambda fmt: None))
    assert client.get("/health").json()["status"] == "ok"
    assert "browser-stream" in client.get("/").text


def test_incoming_call_returns_stream_twiml(settings):
    settings.public_host = "voice.example.com"
    client = TestClient(create_app(settings, agent_factory=lambda fmt: None))
    response = client.post("/incoming-call")
    assert response.headers["content-type"].startswith("application/xml")
    assert '<Stream url="wss://voice.example.com/media-stream"' in response.text


def test_incoming_call_rejects_bad_twilio_signature(settings):
    settings.twilio_auth_token = SecretStr("secret")
    client = TestClient(create_app(settings, agent_factory=lambda fmt: None))
    assert (
        client.post("/incoming-call", headers={"X-Twilio-Signature": "forged"}).status_code == 403
    )


def test_event_translation():
    assert twilio_to_realtime({"event": "media", "media": {"payload": "abc"}}) == {
        "type": "input_audio_buffer.append",
        "audio": "abc",
    }
    assert twilio_to_realtime({"event": "mark"}) is None
    assert realtime_to_twilio({"type": "response.audio.delta", "delta": "x"}, "S1") == {
        "event": "media",
        "streamSid": "S1",
        "media": {"payload": "x"},
    }
    assert realtime_to_twilio({"type": "input_audio_buffer.speech_started"}, "S1") == {
        "event": "clear",
        "streamSid": "S1",
    }
    assert realtime_to_twilio({"type": "response.done"}, "S1") is None


def test_phone_call_end_to_end(settings):
    fake, formats = FakeRealtimeAPI(), []
    client = make_client(settings, fake, formats)

    with client.websocket_connect("/media-stream") as ws:
        ws.send_text(json.dumps({"event": "start", "start": {"streamSid": "MZ1"}}))
        ws.send_text(json.dumps({"event": "media", "media": {"payload": "caller-audio"}}))
        assert ws.receive_json() == {"event": "clear", "streamSid": "MZ1"}  # barge-in
        assert ws.receive_json() == {
            "event": "media",
            "streamSid": "MZ1",
            "media": {"payload": "agent-audio"},
        }
        ws.send_text(json.dumps({"event": "stop"}))
        assert fake.closed.wait(timeout=5)  # hang-up ends the Realtime session

    assert formats == ["g711_ulaw"]
    session = fake.received[0]["session"]
    assert session["input_audio_format"] == session["output_audio_format"] == "g711_ulaw"
    assert session["tools"][0]["name"] == "track_shipment"

    kinds = [e["type"] for e in fake.received]
    assert kinds[:2] == ["session.update", "input_audio_buffer.append"]
    tool_output = next(e for e in fake.received if e["type"] == "conversation.item.create")
    assert tool_output["item"]["call_id"] == "call_1"
    assert "397148 is out for delivery" in tool_output["item"]["output"]
    assert kinds[-1] == "response.create"


@pytest.mark.parametrize("path", ["/browser-stream"])
def test_browser_session_uses_pcm16_and_pushes_ui_state(settings, path):
    fake, formats = FakeRealtimeAPI(), []
    client = make_client(settings, fake, formats)

    with client.websocket_connect(path) as ws:
        ws.send_text(json.dumps({"type": "input_audio_buffer.append", "audio": "caller-audio"}))
        received = [ws.receive_json() for _ in range(3)]
        ws.close()
        # Closing the tab must end the Realtime session (no leaked upstream connection).
        assert fake.closed.wait(timeout=5)

    assert formats == ["pcm16"]
    assert {"type": "tool_output", "name": "track_shipment", "data": ["snapshot"]} in received
    assert {"type": "response.audio.delta", "delta": "agent-audio"} in received
