import os
import json
import asyncio
import websockets
from dotenv import load_dotenv

from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocketDisconnect

from twilio.twiml.voice_response import VoiceResponse, Connect

from langchain_openai_voice import OpenAIVoiceReactAgent
from prompt import INSTRUCTIONS
from tools import TOOLS

load_dotenv()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY') 
PORT = int(os.getenv('PORT', 5050))

app = FastAPI()
# app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running!"}


@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    response = VoiceResponse()
    response.say("Please wait while we connect your call to the A. I. voice assistant.")
    response.pause(length=1)
    response.say("O.K. you can start talking!")
    host = request.url.hostname or 'localhost'
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")



@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections between Twilio and your OpenAIVoiceReactAgent."""
    print("Client connected")
    await websocket.accept()

    # Initialize your OpenAIVoiceReactAgent
    agent = OpenAIVoiceReactAgent(
        model="gpt-4o-realtime-preview-2024-10-01",
        tools=TOOLS,
        instructions=INSTRUCTIONS,
        openai_api_key=OPENAI_API_KEY,  # Pass the API key
    )

    stream_sid = None

    # Create an input_stream generator to feed audio data to the agent
    async def input_stream():
        try:
            async for message in websocket.iter_text():
                data = json.loads(message)
                if data['event'] == 'media':
                    audio_payload = data['media']['payload']
                    # Since we're using g711_ulaw, we can pass the audio payload directly
                    yield json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": audio_payload
                    })
                elif data['event'] == 'start':
                    nonlocal stream_sid
                    stream_sid = data['start']['streamSid']
                    print(f"Incoming stream has started {stream_sid}")
                elif data['event'] == 'stop':
                    print("Stream has ended")
                    break
        except WebSocketDisconnect:
            print("Client disconnected.")
            

    # Define a function to send agent outputs back to Twilio
    async def send_output_chunk(data):
        # data is a JSON string from the agent
        response = json.loads(data)
        if response['type'] == 'response.audio.delta' and response.get('delta'):
            # Since we're using g711_ulaw, we can pass the audio delta directly
            audio_payload = response['delta']
            await websocket.send_json({
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": audio_payload
                }
            })

        elif response['type'] == 'input_audio_buffer.speech_started':
            await websocket.send_json({ 
                "event": "clear",
                "streamSid": stream_sid,
            })
            
        
        elif response['type'] == 'response.audio_transcript.done':
            pass
        
        else:
            print(f"Unhandled agent response type: {response['type']}")

    # Start the agent's aconnect method
    try:
        await agent.aconnect(
            input_stream=input_stream(),
            send_output_chunk=send_output_chunk
        )
    except Exception as e:
        print(f"Error in agent aconnect: {e}")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
