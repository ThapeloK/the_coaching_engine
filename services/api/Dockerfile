# The API image.
#
# Build context is the REPO ROOT, not services/api, because the app imports the
# tested deterministic core from services/agent. Locally that arrives as a
# compose mount; a deployed container has no mounts, so it has to be in the
# image or the service dies on import with a bare ModuleNotFoundError.
#
#   docker build -f services/api/Dockerfile -t ce-api .
#
FROM python:3.12-slim

# psycopg needs no build tools thanks to the binary wheel, but curl earns its
# place: it is how you debug a container that will not answer, from inside.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The reasoning core first: it changes least, so it caches best.
COPY services/agent /agent
ENV PYTHONPATH=/agent

COPY services/api/ /app/

# Guest lines synthesised ahead of time and committed, so a cold start does not
# re-spend the ElevenLabs budget (10,000 characters for the LIFE of the free
# account) and the first guest turn of a demo plays instantly. Absent is fine:
# the conversation is designed to work as text.
COPY services/api/.voice-cache /app/.voice-cache
ENV CE_VOICE_CACHE=/app/.voice-cache

# Render, Cloud Run and Fly all inject the port. Defaulting keeps `docker run`
# working locally without arguments.
ENV PORT=8000
EXPOSE 8000

# Shell form, because $PORT has to be expanded at runtime rather than baked in.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
