FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# PyTorch CPU — smaller image, works everywhere without NVIDIA drivers.
# To use GPU instead, replace this line with the CUDA wheel URL for your CUDA version.
RUN pip install --no-cache-dir \
    torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    "diffusers>=0.30.0" \
    "huggingface_hub>=0.23.0" \
    "transformers>=4.40.0" \
    accelerate \
    fastapi \
    "uvicorn[standard]" \
    Pillow

COPY server.py .

RUN mkdir -p /model-cache

EXPOSE 7860

# start-period gives time for the model to download on first run (~4 GB)
HEALTHCHECK --interval=20s --timeout=10s --start-period=600s \
    CMD curl -sf http://localhost:7860/health | grep -q "ready" || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860", "--timeout-keep-alive", "300"]
