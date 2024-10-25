from typing import AsyncIterator
from starlette.websockets import WebSocket


async def websocket_stream(websocket: WebSocket) -> AsyncIterator[str]:
    try:
        while True:
            try:
                data = await websocket.receive_text()
                yield data
            except Exception as e:
                print(f"An error occurred during stream data: {e}")
                break
    finally:
        try:
            state = websocket.client_state
            print(f"websocket.client_state: {state}")
            if not websocket.client_state == "DISCONNECTED":
                await websocket.close(code=1000)  # Normal closure
        except Exception as e:
            print(f"Error during WebSocket closure: {e}")
        print("WebSocket connection closed.")