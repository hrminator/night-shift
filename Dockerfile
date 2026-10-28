FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/tmp/uv-cache \
    DAILY_CAP_USD=5 \
    RECORDED_JOB="6c7c7c742513"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

RUN useradd --create-home --uid 10001 app

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY app ./app
COPY fixtures ./fixtures
COPY static ./static
COPY data ./data

RUN uv sync --frozen --no-dev && chown -R app:app /app

USER app

# Front-door config: RECORDED_JOB pins the replayed export (empty = latest
# hero run with a wake and a hold); DAILY_CAP_USD caps live-resume model
# spend per UTC day. RUN_TOKEN is a secret: set it with
# `fly secrets set RUN_TOKEN=...`, never bake it into the image.
EXPOSE 8080

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
