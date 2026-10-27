FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/tmp/uv-cache

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

RUN useradd --create-home --uid 10001 app

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY app ./app
COPY fixtures ./fixtures
COPY data ./data

RUN uv sync --frozen --no-dev && chown -R app:app /app

USER app

EXPOSE 8080

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
