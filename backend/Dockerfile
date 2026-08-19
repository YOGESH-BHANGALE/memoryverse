FROM python:3.11-slim

WORKDIR /app

# Thread pools default to the number of cores the *host* exposes, not the CPU
# the container is actually granted. On a shared free-tier box that means many
# worker threads — each with a stack and its own allocator arena — competing for
# 0.1 CPU. Capping them cuts resident memory and thread-churn with no real
# throughput cost, since a fraction of one core is the true bottleneck. The
# ONNX encoder and NumPy's BLAS in the embedding path are the ones that matter.
ENV OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    TOKENIZERS_PARALLELISM=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the ONNX embedding model (all-MiniLM-L6-v2, ~80 MB) so it is
# baked into the image. Otherwise chromadb fetches it on the first request of
# every cold start — slow, and a runtime network dependency that can fail on
# the free tier. Caches to /root/.cache/chroma, which is read back at runtime.
RUN python -c "from chromadb.utils import embedding_functions as ef; ef.DefaultEmbeddingFunction()(['warmup'])"

# Copy application
COPY . .

# Create directories
RUN mkdir -p chroma_db uploads

# Shell form (not exec form) so ${PORT} is expanded at runtime. Render, Fly and
# Cloud Run inject the port they will health-check; a container that binds a
# fixed 8000 is reported as "no open ports detected" and never goes live.
# Falls back to 8000, so docker-compose and local runs are unchanged.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
