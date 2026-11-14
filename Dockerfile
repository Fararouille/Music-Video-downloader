# syntax=docker/dockerfile:1

FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CRATE_HOST=0.0.0.0 \
    CRATE_PORT=8000 \
    CRATE_LIBRARY=/library \
    CRATE_DB=/data/crate.db \
    CRATE_FRONTEND=/app/frontend/dist

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY --from=ui /ui/dist ./frontend/dist

RUN useradd --create-home --uid 10001 crate \
    && mkdir -p /library /data \
    && chown -R crate:crate /library /data /app
USER crate

VOLUME ["/library", "/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

CMD ["crate", "serve", "--host", "0.0.0.0", "--port", "8000"]
