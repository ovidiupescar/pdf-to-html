# ── Stage 1: Build Next.js frontend (static export) ──
FROM node:20-alpine AS frontend-builder

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build
# Output is in /app/out/

# ── Stage 2: Python backend + serve frontend ──
FROM python:3.11-slim

WORKDIR /app

# System dependencies (for docling / torch)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Backend source
COPY backend/ backend/

# Built frontend (copied into a predictable path for FastAPI to serve)
COPY --from=frontend-builder /app/out/ frontend/out/

ENV PYTHONPATH=/app
ENV OUTPUT_DIR=/app/output
ENV PORT=3581

EXPOSE 3581

CMD uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT:-3581}
