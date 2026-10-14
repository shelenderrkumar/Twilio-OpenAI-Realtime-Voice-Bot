FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md main.py ./
COPY voicebot ./voicebot
COPY static ./static
COPY data ./data
# Editable install keeps static/ and data/ resolvable relative to the source tree.
RUN pip install --no-cache-dir -e .

RUN useradd --create-home appuser && chown -R appuser /app/data
USER appuser

EXPOSE 5050
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5050/health')"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5050"]
