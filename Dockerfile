FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PDM_CHECK_UPDATE=false \
    DJANGO_SETTINGS_MODULE=app.settings.prod \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN pip install --no-cache-dir pdm
COPY pyproject.toml pdm.lock ./
RUN pdm install --prod --frozen-lockfile --no-self

COPY . .
RUN SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && useradd --create-home app && chown -R app /app
USER app

EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn app.wsgi:application --bind 0.0.0.0:8000 --workers 3"]
