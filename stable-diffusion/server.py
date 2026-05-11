"""
Minimal Stable Diffusion API server — exposes AUTOMATIC1111-compatible endpoints
so the game master's image_generator.py works unchanged.

Model is loaded eagerly at startup and cached in /model-cache between restarts.
"""

from __future__ import annotations
import base64
import io
import os
from contextlib import asynccontextmanager

import torch
from diffusers import StableDiffusionPipeline
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from PIL import Image

MODEL_ID  = os.getenv("SD_MODEL", "runwayml/stable-diffusion-v1-5")
CACHE_DIR = "/model-cache"

_pipe: StableDiffusionPipeline | None = None
_device = "cpu"
_ready  = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipe, _device, _ready

    _device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype   = torch.float16 if _device == "cuda" else torch.float32

    print(f"[SD] Loading {MODEL_ID} on {_device} — first run downloads ~4 GB, please wait...")

    _pipe = StableDiffusionPipeline.from_pretrained(
        MODEL_ID,
        torch_dtype=dtype,
        cache_dir=CACHE_DIR,
        safety_checker=None,           # skip NSFW filter — saves ~600 MB RAM
        requires_safety_checker=False,
    ).to(_device)

    if _device == "cpu":
        _pipe.enable_attention_slicing()  # reduces peak RAM usage on CPU

    _ready = True
    print(f"[SD] Model ready on {_device}")
    yield
    _pipe = None


app = FastAPI(title="SD Server", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ready" if _ready else "loading", "device": _device}


@app.get("/sdapi/v1/sd-models")
def get_models():
    if not _ready:
        raise HTTPException(503, "Model is still loading — check /health")
    return [{"title": MODEL_ID, "model_name": MODEL_ID, "hash": "", "sha256": ""}]


@app.post("/sdapi/v1/txt2img")
def txt2img(request: dict):
    if not _ready:
        raise HTTPException(503, "Model is still loading")

    # SD 1.5 native resolution is 512×512 — clamp to avoid quality degradation
    width  = min(int(request.get("width",  512)), 512)
    height = min(int(request.get("height", 512)), 512)
    steps  = min(int(request.get("steps",  20)),  50)
    cfg    = float(request.get("cfg_scale", 7.0))

    result = _pipe(
        prompt=request.get("prompt", ""),
        negative_prompt=request.get("negative_prompt", ""),
        num_inference_steps=steps,
        width=width,
        height=height,
        guidance_scale=cfg,
    )

    buf = io.BytesIO()
    result.images[0].save(buf, format="PNG")
    buf.seek(0)
    return {"images": [base64.b64encode(buf.getvalue()).decode()], "info": ""}
