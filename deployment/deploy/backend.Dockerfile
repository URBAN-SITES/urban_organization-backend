FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PDM_CHECK_UPDATE=false DJANGO_SETTINGS_MODULE=app.settings.prod PATH="/app/.venv/bin:$PATH"
WORKDIR /app
RUN pip install --no-cache-dir pdm
COPY pyproject.toml pdm.lock ./
RUN pdm install --prod --frozen-lockfile --no-self
COPY . .
RUN SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && useradd --create-home app && mkdir -p /app/media && chown app:app /app/media
USER app
CMD ["sh", "-c", "python manage.py migrate --noinput && daphne --proxy-headers -b 0.0.0.0 -p 8000 app.asgi:application"]
