FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create directories
RUN mkdir -p chroma_db uploads

# Shell form (not exec form) so ${PORT} is expanded at runtime. Render, Fly and
# Cloud Run inject the port they will health-check; a container that binds a
# fixed 8000 is reported as "no open ports detected" and never goes live.
# Falls back to 8000, so docker-compose and local runs are unchanged.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
