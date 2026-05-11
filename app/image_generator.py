from __future__ import annotations
import base64
import re
import requests

# Points at the sd-server Docker Compose service by name.
# Override with SD_URL env var if using an external AUTOMATIC1111 instance.
import os
SD_URL  = os.getenv("SD_URL", "http://stable-diffusion:7860")
TIMEOUT = 180   # model inference on CPU can be slow

STYLE_BY_SETTING = {
    "High Fantasy":     "fantasy RPG oil painting, epic, detailed, dramatic lighting, Greg Rutkowski, artstation",
    "Dark Fantasy":     "dark gothic fantasy art, grim, moody, atmospheric, Boris Vallejo, detailed shadows",
    "Sci-Fi":           "sci-fi concept art, futuristic environment, cinematic lighting, artstation, hard surface",
    "Post-Apocalyptic": "post-apocalyptic wasteland art, desolate, dramatic sky, concept art, gritty detail",
    "Cyberpunk":        "cyberpunk cityscape, neon reflections, rain-slicked street, cinematic, artstation 8k",
}

NEGATIVE = (
    "nsfw, nude, blurry, low quality, bad anatomy, extra limbs, watermark, "
    "text, signature, cartoon, anime, chibi, deformed, ugly"
)


def _build_prompt(narrative: str, game_state: dict) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", narrative.strip())
    scene = " ".join(sentences[:2]) if sentences else narrative[:250]
    scene = re.sub(r"\b(you|your|you're|you've)\b", "", scene, flags=re.IGNORECASE)
    scene = re.sub(r"\s+", " ", scene).strip()

    world = game_state.get("world", {})
    ctx_parts = [p for p in [
        world.get("current_location", ""),
        world.get("time_of_day", ""),
        world.get("weather", ""),
    ] if p]
    ctx = ", ".join(ctx_parts)

    setting = world.get("setting", "High Fantasy")
    style = STYLE_BY_SETTING.get(setting, STYLE_BY_SETTING["High Fantasy"])

    parts = [p for p in [scene, ctx, style] if p]
    return ", ".join(parts)[:500]


def is_available() -> bool:
    """Returns True only when the model is fully loaded and ready."""
    try:
        r = requests.get(f"{SD_URL}/health", timeout=4)
        return r.status_code == 200 and r.json().get("status") == "ready"
    except Exception:
        return False


def is_loading() -> bool:
    """Returns True when the SD container is up but still downloading/loading the model."""
    try:
        r = requests.get(f"{SD_URL}/health", timeout=4)
        return r.status_code == 200 and r.json().get("status") == "loading"
    except Exception:
        return False


def generate(narrative: str, game_state: dict) -> bytes | None:
    """Call Stable Diffusion txt2img and return PNG bytes, or None if SD is unreachable."""
    try:
        prompt = _build_prompt(narrative, game_state)
        payload = {
            "prompt": prompt,
            "negative_prompt": NEGATIVE,
            "steps": 20,
            "width": 512,   # SD 1.5 native resolution
            "height": 512,
            "cfg_scale": 7,
        }
        resp = requests.post(f"{SD_URL}/sdapi/v1/txt2img", json=payload, timeout=TIMEOUT)
        if resp.status_code == 200:
            images = resp.json().get("images", [])
            if images:
                return base64.b64decode(images[0])
    except Exception:
        pass
    return None
