FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PDM_CHECK_UPDATE=false \
    DJANGO_SETTINGS_MODULE=app.settings.prod \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# ffmpeg extracts the audio of meeting recordings for local transcription
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pdm
COPY pyproject.toml pdm.lock ./
RUN pdm lock && pdm install --prod --frozen-lockfile --no-self

COPY . .
RUN SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && useradd --create-home app && chown -R app /app \
    && mkdir -p /models/whisper && chown app /models/whisper
USER app

EXPOSE 8000
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "app.asgi:application"]
