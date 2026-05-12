FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source
COPY . .

ENV PYTHONPATH=/app
ENV OUTPUT_DIR=/app/output
ENV PORT=8000

EXPOSE 8000

CMD uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
