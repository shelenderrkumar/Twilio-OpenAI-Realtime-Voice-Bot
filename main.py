"""Run the voice agent server: `python main.py` (or `uvicorn main:app`)."""

import logging

import uvicorn

from voicebot.config import get_settings
from voicebot.server import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=get_settings().port)
