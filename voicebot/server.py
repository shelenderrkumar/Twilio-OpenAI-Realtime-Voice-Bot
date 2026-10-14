"""HTTP / WebSocket entry points.

* ``POST /incoming-call``  Twilio voice webhook -> TwiML that opens a Media Stream
* ``WS   /media-stream``   Twilio Media Stream (G.711 mu-law, 8 kHz)
* ``WS   /browser-stream`` Browser microphone demo (PCM16, 24 kHz) served at ``/``
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from twilio.twiml.voice_response import Connect, VoiceResponse

from voicebot import __version__
from voicebot.config import PROJECT_ROOT, Settings, get_settings
from voicebot.dependencies import Dependencies
from voicebot.profiles import build_profile
from voicebot.realtime import RealtimeVoiceAgent

logger = logging.getLogger(__name__)
STATIC_DIR = PROJECT_ROOT / "static"


# --- Twilio <-> Realtime event translation (pure functions, unit-tested) ---------------
def twilio_to_realtime(message: dict[str, Any]) -> dict[str, Any] | None:
    if message.get("event") == "media":
        return {"type": "input_audio_buffer.append", "audio": message["media"]["payload"]}
    return None


def realtime_to_twilio(event: dict[str, Any], stream_sid: str | None) -> dict[str, Any] | None:
    kind = event.get("type")
    if kind == "response.audio.delta" and event.get("delta"):
        return {"event": "media", "streamSid": stream_sid, "media": {"payload": event["delta"]}}
    if kind == "input_audio_buffer.speech_started":
        # Barge-in: the caller started talking, so drop audio Twilio has not played yet.
        return {"event": "clear", "streamSid": stream_sid}
    return None


def create_app(settings: Settings | None = None, agent_factory=None) -> FastAPI:
    settings = settings or get_settings()
    deps = Dependencies(settings)

    def default_agent_factory(audio_format: str) -> RealtimeVoiceAgent:
        profile = build_profile(settings.agent_profile, deps)
        return RealtimeVoiceAgent(
            api_key=settings.openai_api_key.get_secret_value(),
            instructions=profile.instructions,
            tools=profile.tools,
            model=settings.realtime_model,
            url=settings.realtime_url,
            voice=settings.voice,
            audio_format=audio_format,
            max_conversation_items=settings.max_conversation_items,
            state_snapshot=profile.state_snapshot,
        )

    make_agent = agent_factory or default_agent_factory
    app = FastAPI(title="Realtime Voice Agent", version=__version__)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def browser_demo():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health")
    async def health():
        return {"status": "ok", "profile": settings.agent_profile, "version": __version__}

    async def verify_twilio_signature(request: Request) -> None:
        if settings.twilio_auth_token is None:
            return
        from twilio.request_validator import RequestValidator

        validator = RequestValidator(settings.twilio_auth_token.get_secret_value())
        params = dict(await request.form()) if request.method == "POST" else {}
        url = str(request.url)
        if settings.public_host:
            url = str(request.url.replace(scheme="https", netloc=settings.public_host))
        if not validator.validate(url, params, request.headers.get("X-Twilio-Signature", "")):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    @app.api_route("/incoming-call", methods=["GET", "POST"])
    async def incoming_call(request: Request):
        await verify_twilio_signature(request)
        host = settings.public_host or request.url.hostname
        response = VoiceResponse()
        response.say("Please wait while we connect you to the A.I. assistant.")
        response.pause(length=1)
        response.say("O.K. you can start talking!")
        connect = Connect()
        connect.stream(url=f"wss://{host}/media-stream")
        response.append(connect)
        return Response(content=str(response), media_type="application/xml")

    @app.websocket("/media-stream")
    async def media_stream(websocket: WebSocket):
        await websocket.accept()
        stream_sid: str | None = None

        async def caller_audio() -> AsyncIterator[dict[str, Any]]:
            nonlocal stream_sid
            try:
                async for raw in websocket.iter_text():
                    message = json.loads(raw)
                    if message.get("event") == "start":
                        stream_sid = message["start"]["streamSid"]
                        logger.info("Call started, stream %s", stream_sid)
                    elif message.get("event") == "stop":
                        logger.info("Call ended, stream %s", stream_sid)
                        return
                    elif (event := twilio_to_realtime(message)) is not None:
                        yield event
            except WebSocketDisconnect:
                logger.info("Twilio disconnected")

        async def to_twilio(event: dict[str, Any]) -> None:
            if (message := realtime_to_twilio(event, stream_sid)) is not None:
                await websocket.send_json(message)

        await _run_agent(make_agent("g711_ulaw"), caller_audio(), to_twilio)

    @app.websocket("/browser-stream")
    async def browser_stream(websocket: WebSocket):
        await websocket.accept()

        async def mic_audio() -> AsyncIterator[dict[str, Any]]:
            try:
                async for raw in websocket.iter_text():
                    event = json.loads(raw)
                    if event.get("type") == "input_audio_buffer.append":
                        yield event
            except WebSocketDisconnect:
                logger.info("Browser disconnected")

        await _run_agent(make_agent("pcm16"), mic_audio(), websocket.send_json)

    return app


async def _run_agent(agent: RealtimeVoiceAgent, input_events, emit) -> None:
    try:
        await agent.run(input_events, emit)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Voice session failed")
